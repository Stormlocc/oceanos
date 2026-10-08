"""Catálogo SQLite legible (esquema v4): escenas, procesos, búsquedas y eventos."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .config import canonical, file_hash
from .native import acquisition_day, eligible, l1_bytes, scene_date

VERSION = 4

# Los comentarios de las columnas quedan guardados en la base y los muestran los visores SQLite.
SCHEMA = '''
CREATE TABLE IF NOT EXISTS escenas (
 escena TEXT PRIMARY KEY,          -- nombre del producto del proveedor
 sensor TEXT,                      -- sentinel2 | landsat
 satelite TEXT,                    -- S2A, S2B, S2C, L8, L9
 fecha_utc TEXT,                   -- AAAA-MM-DD HH:MM de la adquisición
 tile TEXT,                        -- 19QGV (Sentinel-2) o path+row 005048 (Landsat)
 proveedor TEXT,                   -- CDSE | USGS | LOCAL
 tamano_mb REAL,                   -- tamaño del L1 a descargar
 nubosidad REAL,                   -- % informado por el proveedor
 estado TEXT NOT NULL DEFAULT 'NUEVA', -- NUEVA, PENDIENTE, PROCESADA, FALLIDA, DISPONIBLE, IMPORTADA
 registrada TEXT,                  -- cuándo se puso en la cola (search --registrar)
 vista TEXT,                       -- última búsqueda en que apareció
 adquisicion TEXT,                 -- satélite:día:tile; une la escena con L1R/L2W importados
 fuente TEXT                       -- JSON del proveedor necesario para descargar y verificar
);
CREATE TABLE IF NOT EXISTS procesos (
 id INTEGER PRIMARY KEY,           -- 1, 2, 3…; también da nombre a la carpeta
 escena TEXT REFERENCES escenas(escena),
 aoi TEXT,                         -- región del perfil (lapargera_v1)
 tipo TEXT,                        -- DESCARGA | LOCAL | DERIVADO | IMPORTADO
 estado TEXT,                      -- EN_CURSO, OK, OMITIDO, FALLIDO, INTERRUMPIDO, IMPORTADO
 inicio TEXT,                      -- AAAA-MM-DD HH:MM:SS UTC
 fin TEXT,
 duracion_min REAL,
 descarga_min REAL,
 descarga_mb REAL,
 intentos INTEGER,                 -- intentos de descarga (fallidos + exitoso)
 error TEXT,
 carpeta TEXT,                     -- runs/0007_S2B_2026-02-15
 l1r TEXT,                         -- ruta dentro de storage
 l1r_mb REAL,
 l2w TEXT,
 l2w_mb REAL,
 archivos TEXT,                    -- PRESENTES | FALTAN
 validacion TEXT,                  -- TECNICA_OK | SIN_VERIFICAR (importados) | PENDIENTE
 limpieza TEXT,                    -- PENDIENTE, HECHA, APLAZADA, FALLIDA, NO_APLICA
 l1r_padre INTEGER REFERENCES procesos(id), -- proceso cuyo L1R se reutilizó
 clave_resultado TEXT,             -- reutilización: misma fuente, settings, motor y productos
 clave_correccion TEXT,            -- reutilización de L1R: igual, sin productos
 l1r_bytes INTEGER, l1r_sha256 TEXT, l2w_bytes INTEGER, l2w_sha256 TEXT,
 detalle TEXT DEFAULT '{}'         -- JSON: métricas, validación, ciencia, settings, entorno y perfil
);
CREATE TABLE IF NOT EXISTS busquedas (
 id INTEGER PRIMARY KEY,
 fecha TEXT,
 proveedor TEXT,
 sensor TEXT,
 satelites TEXT,
 desde TEXT,                       -- inicio UTC incluido
 hasta TEXT,                       -- fin UTC excluido
 intento INTEGER,
 estado TEXT,                      -- EN_CURSO, OK, FALLIDA, INTERRUMPIDA
 devueltas INTEGER,                -- escenas devueltas por el proveedor
 cumplen INTEGER,                  -- de ellas, las que cumplen el perfil
 total_proveedor INTEGER,          -- coincidencias que informa el proveedor (USGS totalHits)
 completitud TEXT,                 -- COMPLETE, INCOMPLETE, UNKNOWN
 tamanos TEXT,                     -- origen de los tamaños: OK, M2M, EARTHEXPLORER, NO_DISPONIBLE
 descartadas TEXT,                 -- JSON [{escena, motivo}]
 error TEXT
);
CREATE TABLE IF NOT EXISTS eventos (
 id INTEGER PRIMARY KEY,
 fecha TEXT,
 proceso INTEGER,
 escena TEXT,
 tipo TEXT,
 mensaje TEXT
);
CREATE INDEX IF NOT EXISTS procesos_escena ON procesos(escena);
CREATE INDEX IF NOT EXISTS procesos_resultado ON procesos(clave_resultado);
CREATE INDEX IF NOT EXISTS procesos_correccion ON procesos(clave_correccion);
CREATE INDEX IF NOT EXISTS eventos_proceso ON eventos(proceso);

CREATE VIEW IF NOT EXISTS v_resumen AS
 SELECT 'escenas' AS tabla, estado, count(*) AS cantidad FROM escenas GROUP BY estado
 UNION ALL SELECT 'procesos', estado, count(*) FROM procesos GROUP BY estado;
CREATE VIEW IF NOT EXISTS v_cola AS
 SELECT escena, fecha_utc, satelite, tamano_mb, estado, registrada FROM escenas
 WHERE estado IN ('PENDIENTE','FALLIDA') ORDER BY fecha_utc;
CREATE VIEW IF NOT EXISTS v_descargas AS
 SELECT p.id, e.fecha_utc, e.satelite, p.descarga_min, p.descarga_mb, p.intentos, p.duracion_min,
        p.l1r_mb, p.l2w_mb, p.carpeta, p.escena
 FROM procesos p JOIN escenas e USING (escena) WHERE p.estado='OK' ORDER BY e.fecha_utc;
CREATE VIEW IF NOT EXISTS v_fallidas AS
 SELECT e.escena, e.fecha_utc, e.estado, count(*) AS procesos_fallidos, max(p.intentos) AS max_intentos,
        group_concat(DISTINCT p.error) AS errores, max(p.inicio) AS ultimo
 FROM procesos p JOIN escenas e USING (escena)
 WHERE p.estado IN ('FALLIDO','INTERRUMPIDO') AND e.estado NOT IN ('PROCESADA','IMPORTADA')
 GROUP BY e.escena ORDER BY e.fecha_utc;
CREATE VIEW IF NOT EXISTS v_disco AS
 SELECT CASE tipo WHEN 'IMPORTADO' THEN 'importado' ELSE 'propio' END AS origen,
        count(l1r) AS l1r, round(sum(l1r_mb)/1000.0,2) AS l1r_gb,
        count(l2w) AS l2w, round(sum(l2w_mb)/1000.0,2) AS l2w_gb
 FROM procesos WHERE archivos='PRESENTES' GROUP BY origen;
'''

PLATFORMS = {'LC08': 'L8', 'LC09': 'L9'}


def stamp():
    """Instante UTC legible y ordenable: AAAA-MM-DD HH:MM:SS."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def minutes(start, end):
    """Minutos entre dos marcas de `stamp`, con dos decimales."""
    parse = lambda text: datetime.strptime(text, '%Y-%m-%d %H:%M:%S')
    return round((parse(end)-parse(start)).total_seconds()/60, 2)


def mb(value):
    """Bytes a MB decimales con un decimal (None se conserva)."""
    return None if value is None else round(value/1e6, 1)


def satellite(info):
    """Nombre corto del satélite: S2A/S2B/S2C o L8/L9."""
    return PLATFORMS.get(info['platform'], info['platform'])


def place(info):
    """Tile Sentinel-2 o path+row Landsat."""
    return info.get('tile') or '{:03d}{:03d}'.format(info['path'], info['row'])


def cloud(source):
    """Nubosidad publicada (CDSE `cloudCover` o USGS `Scene Cloud Cover L1`), o None."""
    metadata = source.get('metadata', {})
    for attribute in metadata.get('Attributes', []) or []:
        if attribute.get('Name') == 'cloudCover':
            return round(float(attribute['Value']), 2)
    value = metadata.get('Scene Cloud Cover L1') or metadata.get('Land Cloud Cover')
    try:
        return round(float(value), 2) if value is not None else None
    except ValueError:
        return None


def same_content(old, new):
    """Indica si dos snapshots del proveedor tienen el mismo formato y checksums comparables."""
    pairs = lambda source: sorted((c['Algorithm'].lower(), c['Value'].lower())
                                  for c in source.get('metadata', {}).get('Checksum', []) or [])
    return old.get('format') == new.get('format') and bool(pairs(old)) and pairs(old) == pairs(new)


class Catalog:
    """Acceso al catálogo SQLite en <storage>/catalog/catalog.sqlite."""
    def __init__(self, storage):
        """Abre o crea la base. Un catálogo anterior (v1–v3) se guarda como respaldo y se empieza de cero."""
        self.storage = Path(storage).resolve()
        folder = self.storage/'catalog'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/'catalog.sqlite'
        self.backup = None
        self.db = self.connect(path)
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        old_tables = self.db.execute("SELECT count(*) FROM sqlite_master WHERE name='ejecuciones'").fetchone()[0]
        if version > VERSION:
            raise ValueError('Versión de catálogo no soportada')
        if version in (1, 2, 3) or old_tables:
            self.db.close()
            self.backup = folder/f"catalog_v{version}_respaldo_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.sqlite"
            path.rename(self.backup)
            self.db = self.connect(path)
        self.db.executescript(SCHEMA)
        self.db.execute(f'PRAGMA user_version={VERSION}')

    @staticmethod
    def connect(path):
        """Conexión con filas tipo diccionario y claves foráneas activas."""
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def event(self, kind, message, process=None, scene=None):
        """Registra un evento con mensaje legible, asociado a un proceso y/o una escena."""
        with self.db:
            self.db.execute('INSERT INTO eventos(fecha,proceso,escena,tipo,mensaje) VALUES(?,?,?,?,?)',
                            (stamp(), process, scene, kind, message))

    # ---------- escenas ----------

    def upsert_scene(self, source, seen=True):
        """Inserta o actualiza una escena desde un snapshot del proveedor y devuelve su nombre.

        Conserva el estado y el SHA-256 local ya comprobado si el checksum del proveedor no cambió;
        si cambió, el SHA se descarta para obligar a verificar de nuevo.
        """
        name, info = source['product'], source['identity']
        row = self.db.execute('SELECT fuente FROM escenas WHERE escena=?', (name,)).fetchone()
        if row:
            old = json.loads(row['fuente'])
            if not source.get('sha256') and old.get('sha256'):
                if same_content(old, source):
                    source = {**source, 'sha256': old['sha256']}
                elif old.get('metadata', {}).get('Checksum'):
                    self.event('CONTENIDO_CAMBIADO', 'El checksum del proveedor cambió; se verificará al descargar', scene=name)
        columns = {'sensor': info['family'], 'satelite': satellite(info), 'fecha_utc': scene_date(source),
                   'tile': place(info), 'proveedor': source['provider'], 'tamano_mb': mb(l1_bytes(source)),
                   'nubosidad': cloud(source), 'adquisicion': acquisition_day(info), 'fuente': canonical(source)}
        if seen:
            columns['vista'] = stamp()
        with self.db:
            if row:
                self.db.execute('UPDATE escenas SET '+','.join(f'{k}=?' for k in columns)+' WHERE escena=?',
                                (*columns.values(), name))
            else:
                self.db.execute(f"INSERT INTO escenas(escena,{','.join(columns)}) VALUES(?{',?'*len(columns)})",
                                (name, *columns.values()))
        if not row and source['provider'] != 'LOCAL':
            self.absorb_local(name, columns['adquisicion'])
        return name

    def absorb_local(self, scene, acquisition):
        """Pasa a la escena del proveedor los procesos de una escena LOCAL (creada por sync) de la misma adquisición."""
        for local in self.db.execute("SELECT escena, estado FROM escenas WHERE proveedor='LOCAL' AND adquisicion=?",
                                     (acquisition,)).fetchall():
            with self.db:
                self.db.execute('UPDATE procesos SET escena=? WHERE escena=?', (scene, local['escena']))
                self.db.execute('UPDATE eventos SET escena=? WHERE escena=?', (scene, local['escena']))
                self.db.execute('UPDATE escenas SET estado=? WHERE escena=?', (local['estado'], scene))
                self.db.execute('DELETE FROM escenas WHERE escena=?', (local['escena'],))
            self.event('ESCENA_UNIFICADA', f"{local['escena']} (creada por sync) es {scene}", scene=scene)

    def source(self, scene):
        """Snapshot JSON de la fuente de una escena."""
        row = self.db.execute('SELECT fuente FROM escenas WHERE escena=?', (scene,)).fetchone()
        if not row:
            raise ValueError('Escena no encontrada: '+scene)
        return json.loads(row['fuente'])

    def scene_state(self, scene, state):
        """Cambia el estado de una escena."""
        with self.db:
            self.db.execute('UPDATE escenas SET estado=? WHERE escena=?', (state, scene))

    def resolve_scene(self, text):
        """Nombre completo de una escena a partir del nombre o de un fragmento único (p. ej. 20260215)."""
        exact = self.db.execute('SELECT escena FROM escenas WHERE escena=?', (text,)).fetchone()
        if exact:
            return exact['escena']
        found = [r['escena'] for r in self.db.execute('SELECT escena FROM escenas WHERE escena LIKE ? ORDER BY fecha_utc',
                                                        ('%'+text+'%',))]
        if len(found) != 1:
            raise ValueError(('Escena inexistente: ' if not found else 'Fragmento ambiguo, coincide con: ')
                             + (text if not found else ', '.join(found[:5])))
        return found[0]

    def enqueue(self, scenes):
        """Pone escenas en la cola (estado PENDIENTE); las ya procesadas no se reactivan."""
        with self.db:
            for scene in scenes:
                self.db.execute("UPDATE escenas SET estado='PENDIENTE',registrada=? WHERE escena=? "
                                "AND estado NOT IN ('PROCESADA','IMPORTADA')", (stamp(), scene))
        return len(scenes)

    def dequeue(self, scene):
        """Retira una escena de la cola si aún no se procesó (vuelve a NUEVA)."""
        with self.db:
            self.db.execute("UPDATE escenas SET estado='NUEVA',registrada=NULL WHERE escena=? "
                            "AND estado IN ('PENDIENTE','FALLIDA')", (scene,))

    def queue(self):
        """Escenas registradas alguna vez en la cola, con su número de procesos, ordenadas por fecha."""
        rows = self.db.execute('''SELECT e.*, (SELECT count(*) FROM procesos p WHERE p.escena=e.escena) AS procesos,
            (SELECT max(id) FROM procesos p WHERE p.escena=e.escena) AS ultimo
            FROM escenas e WHERE e.registrada IS NOT NULL ORDER BY e.fecha_utc''').fetchall()
        return [dict(row) for row in rows]

    def completed(self, region):
        """Adquisiciones con L2W presente para la región (propias o importadas); solo comprueba existencia y tamaño."""
        rows = self.db.execute('''SELECT p.id, p.l2w, p.l2w_bytes, e.adquisicion FROM procesos p
            JOIN escenas e USING (escena) WHERE p.l2w IS NOT NULL AND p.archivos='PRESENTES'
            AND p.estado IN ('OK','IMPORTADO') AND p.aoi=?''', (region,)).fetchall()
        done = {}
        for row in rows:
            path = self.storage/row['l2w']
            if path.is_file() and path.stat().st_size == row['l2w_bytes']:
                done[row['adquisicion']] = row['l2w']
            else:
                self.missing(row['id'])
        return done

    def pending(self, config, force=False):
        """Escenas de la cola por procesar (PENDIENTE o FALLIDA) dentro del perfil.

        Las que ya tienen L2W pasan a DISPONIBLE, salvo con `force`. Devuelve
        (por procesar, fuera del perfil, ya disponibles).
        """
        done = {} if force else self.completed(config['aoi']['id'])
        ready, outside, available = [], [], []
        for row in self.db.execute("SELECT escena, adquisicion, fuente FROM escenas "
                                   "WHERE estado IN ('PENDIENTE','FALLIDA') ORDER BY fecha_utc").fetchall():
            if row['adquisicion'] in done:
                self.scene_state(row['escena'], 'DISPONIBLE')
                available.append(row['escena'])
            elif eligible(json.loads(row['fuente']), config):
                ready.append(row['escena'])
            else:
                outside.append(row['escena'])
        return ready, outside, available

    # ---------- búsquedas ----------

    def search_start(self, provider, config, attempt):
        """Registra un intento de búsqueda EN_CURSO y devuelve su id."""
        with self.db:
            cursor = self.db.execute('''INSERT INTO busquedas(fecha,proveedor,sensor,satelites,desde,hasta,intento,estado)
                VALUES(?,?,?,?,?,?,?,'EN_CURSO')''', (stamp(), provider, config['family'], ','.join(config['search']['platforms']),
                config['start'][:19].replace('T', ' '), config['end'][:19].replace('T', ' '), attempt))
        return cursor.lastrowid

    def search_finish(self, search, state, report=None, error=None):
        """Cierra una búsqueda con su resultado (report de native.query) o su error."""
        report = report or {}
        excluded = [{'escena': e['product'], 'motivo': e['reason']} for e in report.get('excluded_by_profile', [])]
        with self.db:
            self.db.execute('''UPDATE busquedas SET estado=?,devueltas=?,cumplen=?,total_proveedor=?,completitud=?,
                tamanos=?,descartadas=?,error=? WHERE id=?''',
                (state, report.get('returned'), report.get('count'), (report.get('provider_counts') or {}).get('totalHits'),
                 report.get('completeness'), report.get('sizes'), canonical(excluded) if excluded else None, error, search))

    # ---------- procesos ----------

    def start(self, scene, kind, config, result_key=None, correction_key=None):
        """Crea un proceso EN_CURSO con su carpeta legible (runs/0007_S2B_2026-02-15) y devuelve su id."""
        row = self.db.execute('SELECT satelite, fecha_utc FROM escenas WHERE escena=?', (scene,)).fetchone()
        with self.db:
            cursor = self.db.execute('''INSERT INTO procesos(escena,aoi,tipo,estado,inicio,validacion,limpieza,
                clave_resultado,clave_correccion,detalle) VALUES(?,?,?,'EN_CURSO',?,'PENDIENTE','PENDIENTE',?,?,?)''',
                (scene, config['aoi']['id'], kind, stamp(), result_key, correction_key, canonical({'perfil': config})))
            process = cursor.lastrowid
            folder = f"runs/{process:04d}_{row['satelite']}_{row['fecha_utc'][:10]}"
            self.db.execute('UPDATE procesos SET carpeta=? WHERE id=?', (folder, process))
        self.event('INICIO', f'Proceso {kind.lower()} de {scene}', process, scene)
        return process

    def process(self, process):
        """Fila de un proceso como diccionario."""
        row = self.db.execute('SELECT * FROM procesos WHERE id=?', (process,)).fetchone()
        if not row:
            raise ValueError(f'Proceso inexistente: {process}')
        return dict(row)

    def update(self, process, **columns):
        """Actualiza columnas de un proceso."""
        with self.db:
            self.db.execute('UPDATE procesos SET '+','.join(f'{k}=?' for k in columns)+' WHERE id=?',
                            (*columns.values(), process))

    def detail(self, process, **values):
        """Agrega claves al JSON `detalle` de un proceso."""
        current = json.loads(self.process(process)['detalle'] or '{}')
        self.update(process, detalle=canonical({**current, **values}))

    def finish(self, process, state, validation=None, error=None, **detail):
        """Cierra un proceso con estado, validación, error y detalle; calcula la duración."""
        row = self.process(process)
        end = stamp()
        self.update(process, estado=state, fin=end, duracion_min=minutes(row['inicio'], end), error=error,
                    validacion=validation or row['validacion'])
        if detail:
            self.detail(process, **detail)
        self.event(state, f'Proceso terminado: {state}' + (f' ({error})' if error else ''), process, row['escena'])

    def downloaded(self, process, seconds, size, attempts):
        """Guarda minutos y MB de la descarga exitosa y el número de intentos."""
        self.update(process, descarga_min=None if seconds is None else round(seconds/60, 2),
                    descarga_mb=mb(size), intentos=attempts)

    def artifact(self, process, kind, path, hashed=True):
        """Registra el L1R o L2W de un proceso (ruta, tamaño y SHA-256)."""
        path = Path(path).resolve()
        size = path.stat().st_size
        level = kind.lower()
        self.update(process, **{level: str(path.relative_to(self.storage)), f'{level}_mb': mb(size),
                                f'{level}_bytes': size, f'{level}_sha256': file_hash(path) if hashed else None},
                    archivos='PRESENTES')

    def missing(self, process):
        """Marca que faltan archivos de un proceso."""
        self.update(process, archivos='FALTAN')

    def available(self, row, kind):
        """Comprueba que el L1R/L2W de un proceso sigue en disco sin cambios; si no, marca FALTAN.

        Sin SHA-256 (importado sin --hash) solo se comparan existencia y tamaño.
        """
        level = kind.lower()
        if not row[level]:
            return False
        path = (self.storage/row[level]).resolve()
        ok = path.is_relative_to(self.storage) and path.is_file() and path.stat().st_size == row[f'{level}_bytes']
        ok = ok and (row[f'{level}_sha256'] is None or file_hash(path) == row[f'{level}_sha256'])
        if not ok:
            self.missing(row['id'])
        return ok

    def reusable(self, key, correction=False):
        """Proceso OK con salida verificada reutilizable: L2W por clave_resultado o L1R por clave_correccion."""
        column, kind = ('clave_correccion', 'L1R') if correction else ('clave_resultado', 'L2W')
        rows = self.db.execute(f'''SELECT * FROM procesos WHERE {column}=? AND estado='OK'
            AND validacion='TECNICA_OK' AND {kind.lower()} IS NOT NULL ORDER BY id DESC''', (key,)).fetchall()
        for row in rows:
            if self.available(row, kind):
                return {'proceso': row['id'], 'ruta': row[kind.lower()]}
        return None

    def failed_attempts(self, process):
        """Intentos de descarga fallidos registrados para un proceso."""
        return self.db.execute("SELECT count(*) FROM eventos WHERE proceso=? AND tipo='INTENTO_FALLIDO'",
                               (process,)).fetchone()[0]

    def runs(self, state=None, last=None):
        """Lista procesos en orden cronológico, opcionalmente por estado o solo los últimos N."""
        rows = self.db.execute('''SELECT p.id, e.fecha_utc, e.satelite, p.tipo, p.estado, p.inicio, p.duracion_min,
            p.descarga_min, p.intentos, p.error, p.l2w, p.archivos, p.escena FROM procesos p
            LEFT JOIN escenas e USING (escena) WHERE ? IS NULL OR p.estado=? ORDER BY p.id DESC LIMIT ?''',
            (state, state, -1 if last is None else last)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def run_detail(self, process):
        """Un proceso con sus columnas, métricas y eventos (id numérico, p. ej. 7 o 0007)."""
        try:
            process = int(str(process).split('_')[0])
        except ValueError:
            raise ValueError(f'Proceso inexistente: {process}') from None
        row = self.process(process)
        detail = json.loads(row.pop('detalle') or '{}')
        detail.pop('perfil', None)
        row['metricas'] = detail.get('metrics', [])
        row['eventos'] = [f"{e['fecha']}  {e['tipo']}: {e['mensaje']}" for e in
                          self.db.execute('SELECT * FROM eventos WHERE proceso=? ORDER BY id', (process,))]
        return row

    def recover(self):
        """Marca INTERRUMPIDO lo que quedó EN_CURSO (procesos y búsquedas) y devuelve cuántos procesos marcó."""
        rows = self.db.execute("SELECT id FROM procesos WHERE estado='EN_CURSO'").fetchall()
        for row in rows:
            self.finish(row['id'], 'INTERRUMPIDO', error='Interrupción detectada al recuperar')
        with self.db:
            self.db.execute("UPDATE busquedas SET estado='INTERRUMPIDA' WHERE estado='EN_CURSO'")
        return len(rows)

    def disk(self, processes=None):
        """MB y número de L1R/L2W presentes, de todo el storage o solo de los procesos dados."""
        usage = {'L1R': [0, 0], 'L2W': [0, 0]}
        for row in self.db.execute("SELECT id, l1r_bytes, l2w_bytes FROM procesos WHERE archivos='PRESENTES'"):
            if processes is None or row['id'] in processes:
                for kind in usage:
                    if row[f'{kind.lower()}_bytes']:
                        usage[kind][0] += 1
                        usage[kind][1] += row[f'{kind.lower()}_bytes']
        return {kind: {'archivos': count, 'bytes': size} for kind, (count, size) in usage.items()}

    def stage_seconds(self, stage):
        """Mediana histórica de segundos de una etapa exitosa; sirve para estimar el progreso."""
        values = sorted(m['seconds'] for (detail,) in self.db.execute("SELECT detalle FROM procesos WHERE estado='OK'")
                        for m in json.loads(detail or '{}').get('metrics', []) if m.get('stage') == stage and m.get('ok'))
        return values[len(values)//2] if values else None
