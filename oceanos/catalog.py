"""Catálogo SQLite legible (esquema v6): escenas, procesos, productos por zona, compuestos y eventos."""
import contextlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .config import canonical, file_hash
from .native import acquisition_day, eligible, l1_bytes, scene_date

VERSION = 6
# AOI anteriores: sus procesos se conservan como legado y nunca cuentan para el AOI nuevo.
LEGACY_AOIS = ('lapargera_v1',)
# Resultados de una zona que cierran su procesamiento (OK con productos, o sin nada que guardar).
TERMINAL = ('OK', 'NUBOSA', 'SIN_DATOS')

# Los comentarios de las columnas quedan guardados en la base y los muestran los visores SQLite.
SCHEMA = '''
CREATE TABLE IF NOT EXISTS escenas (
 escena TEXT PRIMARY KEY,          -- nombre del producto del proveedor
 sensor TEXT,                      -- sentinel2 | landsat | olci
 satelite TEXT,                    -- S2A, S2B, S2C, L8, L9, S3A, S3B
 fecha_utc TEXT,                   -- AAAA-MM-DD HH:MM de la adquisición
 tile TEXT,                        -- 19QGV (Sentinel-2) o path+row 005048 (Landsat)
 proveedor TEXT,                   -- CDSE | USGS | LOCAL
 tamano_mb REAL,                   -- tamaño del L1 a descargar
 nubosidad REAL,                   -- % informado por el proveedor
 estado TEXT NOT NULL DEFAULT 'NUEVA', -- NUEVA, PENDIENTE, PROCESADA, FALLIDA, DISPONIBLE (IMPORTADA: legado v4)
 registrada TEXT,                  -- cuándo se puso en la cola (search --registrar)
 vista TEXT,                       -- última búsqueda en que apareció
 adquisicion TEXT,                 -- satélite:día:tile; une la escena con L1R/L2W importados
 fuente TEXT,                      -- JSON del proveedor necesario para descargar y verificar
 zonas TEXT                        -- JSON: zonas del AOI que toca la escena (según el perfil)
);
CREATE TABLE IF NOT EXISTS procesos (
 id INTEGER PRIMARY KEY,           -- 1, 2, 3…; también da nombre a la carpeta
 escena TEXT REFERENCES escenas(escena),
 aoi TEXT,                         -- región del perfil (water2coast_v1; lapargera_v1 es legado)
 tipo TEXT,                        -- DESCARGA | LOCAL | DERIVADO | IMPORTADO
 estado TEXT,                      -- EN_CURSO, OK, OMITIDO, FALLIDO, INTERRUMPIDO, IMPORTADO
 inicio TEXT,                      -- AAAA-MM-DD HH:MM:SS UTC
 fin TEXT,
 duracion_min REAL,
 descarga_min REAL,
 descarga_mb REAL,
 intentos INTEGER,                 -- intentos de descarga (fallidos + exitoso)
 error TEXT,
 carpeta TEXT,                     -- legado: runs/0007_S2B_2026-02-15 (la superimagen va en productos_escena)
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
 detalle TEXT DEFAULT '{}',        -- JSON: métricas, validación, ciencia, settings, entorno y perfil
 legado INTEGER DEFAULT 0          -- 1: AOI anterior (lapargera_v1, glint apagado); fuera de la superimagen
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
 error TEXT,
 aoi TEXT                          -- región del perfil buscado
);
CREATE TABLE IF NOT EXISTS eventos (
 id INTEGER PRIMARY KEY,
 fecha TEXT,
 proceso INTEGER,
 escena TEXT,
 tipo TEXT,
 mensaje TEXT
);
CREATE TABLE IF NOT EXISTS productos_escena (
 id INTEGER PRIMARY KEY,
 escena TEXT REFERENCES escenas(escena),
 proceso INTEGER REFERENCES procesos(id),
 aoi TEXT,
 zona TEXT,
 sensor TEXT,                      -- S2, Landsat, OLCI
 satelite TEXT,
 fecha TEXT,                       -- AAAA-MM-DD UTC de la adquisición
 instante_utc TEXT,
 estado TEXT,                      -- OK, NUBOSA (nubes sobre el máximo), SIN_DATOS (la escena no cubre la zona)
 carpeta TEXT,                     -- superimagen/escenas/<zona>/<sensor>/<fecha>_<lugar>
 bytes INTEGER,
 variables TEXT,                   -- JSON: COG exportados
 nubes_pct REAL,                   -- % de nubes sobre la zona
 nubes_origen TEXT,                -- MSK_CLASSI_B00, QA_PIXEL o l2_flags
 cobertura_pct REAL,               -- % del polígono de la zona con datos
 agua_vista_pct REAL,              -- % del agua de la zona dentro de la escena
 angulo_glint_deg REAL,            -- media sobre el agua de la zona
 proveedor_id TEXT,                -- Id de CDSE o entityId de USGS
 sha256 TEXT,                      -- SHA-256 de la descarga
 checksum_proveedor TEXT,          -- JSON: checksums publicados por el proveedor
 baseline TEXT,                    -- baseline (S2 N05xx), colección (Landsat 02:T1) o versión (OLCI)
 via_descarga TEXT,                -- CDSE, M2M o EARTHEXPLORER (EARTHEXPLORER:<motivo> si M2M falló)
 acolite TEXT,                     -- JSON: revisión y parche de ACOLITE
 settings TEXT,                    -- JSON: settings nativos usados
 auxiliares TEXT,                  -- JSON: ozono, vapor, presión y viento usados por ACOLITE
 correccion TEXT,                  -- JSON: modelo y AOT 550 del DSF, sza/vza/raa de la escena y medias de aot_550/vza/raa en el agua de la zona
 mascara TEXT,                     -- capa de tierra y versión
 fecha_proceso TEXT,
 UNIQUE(escena, zona, aoi)
);
CREATE TABLE IF NOT EXISTS mascaras (
 zona TEXT, sensor TEXT, resolucion_m INTEGER,
 ruta TEXT, capa TEXT, sha256 TEXT, tierra_pct REAL, fecha TEXT,
 PRIMARY KEY(zona, sensor, resolucion_m)
);
CREATE TABLE IF NOT EXISTS compuestos (
 id INTEGER PRIMARY KEY,
 tipo TEXT,                        -- sargazo_diario, mensual, estacional, anual
 metodo TEXT,                      -- maximo_fai, mejor_pixel, media_ponderada
 aoi TEXT, zona TEXT, sensor TEXT,
 periodo TEXT,                     -- AAAA-MM-DD, AAAA-MM, AAAA-DEF…, AAAA
 carpeta TEXT,
 firma TEXT,                       -- SHA-256 de entradas y parámetros: igual firma, nada que rehacer
 bytes INTEGER,
 n_escenas INTEGER,
 fecha_proceso TEXT,
 detalle TEXT,
 UNIQUE(tipo, metodo, aoi, zona, sensor, periodo)
);
CREATE TABLE IF NOT EXISTS compuesto_escenas (
 compuesto INTEGER REFERENCES compuestos(id) ON DELETE CASCADE,
 producto INTEGER REFERENCES productos_escena(id),
 PRIMARY KEY(compuesto, producto)
);
CREATE INDEX IF NOT EXISTS procesos_escena ON procesos(escena);
CREATE INDEX IF NOT EXISTS productos_zona ON productos_escena(aoi, zona, sensor, fecha);
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
CREATE VIEW IF NOT EXISTS v_superimagen AS
 SELECT aoi, zona, sensor, estado, count(*) AS escenas, round(sum(coalesce(bytes,0))/1e9,2) AS gb,
        min(fecha) AS desde, max(fecha) AS hasta
 FROM productos_escena GROUP BY aoi, zona, sensor, estado;
CREATE VIEW IF NOT EXISTS v_compuestos AS
 SELECT tipo, metodo, zona, sensor, periodo, n_escenas, round(bytes/1e6,1) AS mb, fecha_proceso, carpeta
 FROM compuestos ORDER BY tipo, zona, sensor, periodo;
CREATE VIEW IF NOT EXISTS v_legado AS
 SELECT p.id, p.aoi, e.fecha_utc, e.satelite, p.tipo, p.estado, p.l1r, p.l2w, p.escena
 FROM procesos p LEFT JOIN escenas e USING (escena) WHERE p.legado=1 ORDER BY e.fecha_utc;
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
        """Abre o crea la base.

        Un catálogo v1–v3 se guarda como respaldo y se empieza de cero. Uno v4 o v5 se migra en el
        sitio después de copiarlo como respaldo: en v4 los procesos de AOI anteriores quedan como
        legado; v5 gana la columna `correccion` (vacía en los productos ya exportados).
        """
        self.storage = Path(storage).resolve()
        folder = self.storage/'catalog'
        folder.mkdir(parents=True, exist_ok=True)
        path = folder/'catalog.sqlite'
        self.backup, self.migrated, self.migrated_from = None, False, None
        self.db = self.connect(path)
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        old_tables = self.db.execute("SELECT count(*) FROM sqlite_master WHERE name='ejecuciones'").fetchone()[0]
        if version > VERSION:
            raise ValueError('Versión de catálogo no soportada')
        moment = f'{datetime.now(timezone.utc):%Y%m%d_%H%M%S}'
        if version in (1, 2, 3) or old_tables:
            self.db.close()
            self.backup = folder/f"catalog_v{version}_respaldo_{moment}.sqlite"
            path.rename(self.backup)
            self.db = self.connect(path)
        elif version in (4, 5):
            self.backup = folder/f'catalog_v{version}_respaldo_{moment}.sqlite'
            with contextlib.closing(sqlite3.connect(self.backup)) as copy:
                self.db.backup(copy)
            if version == 4:
                self.migrate_v4()
            else:
                self.migrate_v5()
            self.migrated, self.migrated_from = True, version
        self.db.executescript(SCHEMA)
        self.db.execute(f'PRAGMA user_version={VERSION}')

    def migrate_v4(self):
        """Agrega zonas y legado y deja las escenas libres para el AOI nuevo.

        El estado de cola de una escena (PROCESADA, IMPORTADA…) venía del AOI anterior: con el AOI
        nuevo la misma escena debe poder procesarse por zona. Sus procesos quedan como legado.
        """
        with self.db:
            self.db.execute('ALTER TABLE escenas ADD COLUMN zonas TEXT')
            self.db.execute('ALTER TABLE procesos ADD COLUMN legado INTEGER DEFAULT 0')
            self.db.execute('ALTER TABLE busquedas ADD COLUMN aoi TEXT')
            marks = ','.join('?'*len(LEGACY_AOIS))
            count = self.db.execute(f'UPDATE procesos SET legado=1 WHERE aoi IN ({marks})', LEGACY_AOIS).rowcount
            self.db.execute("UPDATE escenas SET estado='NUEVA', registrada=NULL")
        self.event('LEGADO', f"{count} procesos de {', '.join(LEGACY_AOIS)} (glint apagado) quedan como legado: "
                             'se conservan y no entran a la superimagen')

    def migrate_v5(self):
        """Agrega `correccion` a productos_escena; los productos ya exportados la tienen vacía."""
        with self.db:
            self.db.execute('ALTER TABLE productos_escena ADD COLUMN correccion TEXT')
        self.event('MIGRACION', 'Catálogo v5 → v6: nueva columna productos_escena.correccion (AOT y geometría); '
                                'vacía en los productos exportados antes de la migración')

    @staticmethod
    def connect(path):
        """Conexión con filas tipo diccionario y claves foráneas activas.

        WAL y espera de hasta 60 s permiten una conexión por escena en paralelo: los lectores
        no bloquean al escritor y las escrituras breves se turnan.
        """
        db = sqlite3.connect(path, timeout=60)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=WAL')
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

    def set_zones(self, scene, zones):
        """Guarda las zonas del AOI que toca la escena (las decide el perfil al buscar)."""
        with self.db:
            self.db.execute('UPDATE escenas SET zonas=? WHERE escena=?', (canonical(sorted(zones)), scene))

    def enqueue(self, scenes, done=None):
        """Pone escenas en la cola (estado PENDIENTE) y devuelve (registradas, omitidas {escena: motivo}).

        `done` son las adquisiciones ya completas en el AOI (`completed`). Una adquisición
        (satélite:día:tile) entra una sola vez: se omite si ya está completa o si otra escena suya
        ya está en la cola; entre varias versiones del mismo producto (reprocesos del proveedor)
        entra la más reciente. El estado heredado de la escena no cuenta: una escena del AOI
        anterior se procesa de nuevo para el AOI vigente. Así `run` nunca descarga algo que ya tenemos.
        """
        done = done or {}
        rows = [self.db.execute('SELECT escena, adquisicion, estado FROM escenas WHERE escena=?', (scene,)).fetchone()
                for scene in dict.fromkeys(scenes)]
        queued, skipped, taken = [], {}, {}
        # Más reciente primero: el nombre lleva baseline (N05xx) e instante de generación.
        for row in sorted((row for row in rows if row), key=lambda row: row['escena'], reverse=True):
            scene, acquisition = row['escena'], row['adquisicion']
            if acquisition in done:
                skipped[scene] = 'su adquisición ya está procesada en todas sus zonas'
                continue
            other = taken.get(acquisition) or self.db.execute(
                "SELECT escena FROM escenas WHERE adquisicion=? AND escena!=? AND estado IN ('PENDIENTE','FALLIDA')",
                (acquisition, scene)).fetchone()
            if other:
                skipped[scene] = 'otra versión de la misma adquisición ya está en la cola: ' + (
                    other if isinstance(other, str) else other['escena'])
                continue
            taken[acquisition] = scene
            queued.append(scene)
        with self.db:
            for scene in queued:
                self.db.execute("UPDATE escenas SET estado='PENDIENTE',registrada=? WHERE escena=?", (stamp(), scene))
        return queued, skipped

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

    def report(self, sensor=None):
        """Una fila por escena trabajada (en cola alguna vez o con procesos): resultado y último proceso.

        Resultado: OK, DISPONIBLE (la adquisición ya estaba completa), FALLIDA (el próximo run la
        reintenta) o PENDIENTE, con intentos de descarga, motivo del último fallo y el resultado de
        cada zona. Los procesos de legado no cuentan (ver `legacy`).
        """
        rows = self.db.execute('''SELECT e.escena, e.sensor, e.satelite, e.fecha_utc, e.tile, e.estado,
              p.id AS proceso, p.estado AS proceso_estado, p.intentos, p.error, p.fin, p.descarga_min,
              (SELECT count(*) FROM procesos q WHERE q.escena=e.escena AND q.legado=0) AS procesos,
              (SELECT group_concat(z.zona || ':' || z.estado, ' ') FROM productos_escena z WHERE z.escena=e.escena) AS zonas
            FROM escenas e LEFT JOIN procesos p ON p.id=(SELECT max(id) FROM procesos q WHERE q.escena=e.escena AND q.legado=0)
            WHERE (e.registrada IS NOT NULL OR p.id IS NOT NULL) AND (? IS NULL OR e.sensor=?)
            ORDER BY e.fecha_utc''', (sensor, sensor)).fetchall()
        names = {'PROCESADA': 'OK'}
        return [{**dict(row), 'resultado': names.get(row['estado'], row['estado'])} for row in rows]

    def legacy(self):
        """Procesos de AOI anteriores (legado): se conservan aparte y nunca entran a la superimagen."""
        return [dict(row) for row in self.db.execute('SELECT * FROM v_legado')]

    def completed(self, region, zones=None):
        """Adquisiciones que ya no hay que descargar para la región: {adquisición: zonas terminadas}.

        Una adquisición está completa cuando todas las zonas que toca (o las de `zones`) tienen
        resultado terminal (OK, NUBOSA o SIN_DATOS). El legado nunca cuenta: sus L2W no son productos
        de la superimagen.
        """
        finished = {}
        for row in self.db.execute(f'''SELECT e.adquisicion, z.zona FROM productos_escena z JOIN escenas e USING (escena)
                                        WHERE z.aoi=? AND z.estado IN {TERMINAL}''', (region,)):
            finished.setdefault(row['adquisicion'], set()).add(row['zona'])
        done = {}
        for row in self.db.execute('SELECT adquisicion, zonas FROM escenas WHERE zonas IS NOT NULL'):
            needed = set(json.loads(row['zonas']))
            needed = needed & set(zones) if zones else needed
            if needed and needed <= finished.get(row['adquisicion'], set()):
                done[row['adquisicion']] = 'superimagen: '+', '.join(sorted(needed))
        return done

    def zones_done(self, acquisition, region):
        """Zonas de una adquisición con resultado terminal en la región (cualquier versión del producto)."""
        return {row['zona'] for row in self.db.execute(f'''SELECT z.zona FROM productos_escena z JOIN escenas e USING (escena)
            WHERE e.adquisicion=? AND z.aoi=? AND z.estado IN {TERMINAL}''', (acquisition, region))}

    def pending(self, config, force=False):
        """Escenas de la cola por procesar (PENDIENTE o FALLIDA) dentro del perfil.

        Las ya completas pasan a DISPONIBLE, salvo con `force`. De una misma adquisición se
        procesa una sola escena por run (la más reciente); las demás esperan en la cola y el
        siguiente run las marca DISPONIBLE si aquella termina bien. Devuelve
        (por procesar, fuera del perfil, ya disponibles, aplazadas por repetir adquisición).
        """
        done = {} if force else self.completed(config['aoi']['id'], config['zones'])
        ready, outside, available, deferred, taken = [], [], [], [], set()
        rows = self.db.execute("SELECT escena, adquisicion, fuente FROM escenas "
                               "WHERE estado IN ('PENDIENTE','FALLIDA') ORDER BY fecha_utc, escena DESC").fetchall()
        for row in rows:
            if not eligible(json.loads(row['fuente']), config):
                outside.append(row['escena'])
            elif row['adquisicion'] in done:
                self.scene_state(row['escena'], 'DISPONIBLE')
                available.append(row['escena'])
            elif row['adquisicion'] in taken:
                deferred.append(row['escena'])
            else:
                taken.add(row['adquisicion'])
                ready.append(row['escena'])
        return ready, outside, available, deferred

    # ---------- búsquedas ----------

    def search_start(self, provider, config, attempt):
        """Registra un intento de búsqueda EN_CURSO y devuelve su id."""
        with self.db:
            cursor = self.db.execute('''INSERT INTO busquedas(fecha,proveedor,sensor,satelites,desde,hasta,intento,estado,aoi)
                VALUES(?,?,?,?,?,?,?,'EN_CURSO',?)''', (stamp(), provider, config['family'], ','.join(config['search']['platforms']),
                config['start'][:19].replace('T', ' '), config['end'][:19].replace('T', ' '), attempt, config['aoi']['id']))
        return cursor.lastrowid

    def searched(self, region, sensor, first, last):
        """Indica si búsquedas OK de la región y el sensor cubren todo [first, last) ('AAAA-MM-DD HH:MM:SS').

        Sin esa cobertura no se sabe si faltan escenas del periodo, y su compuesto no está completo.
        """
        reached = first
        for row in self.db.execute("SELECT desde, hasta FROM busquedas WHERE aoi=? AND sensor=? AND estado='OK' "
                                   "ORDER BY desde", (region, sensor)):
            if row['desde'] > reached:
                break
            reached = max(reached, row['hasta'])
        return reached >= last

    def unfinished(self, region, sensor, zone, first, last):
        """Escenas del sensor en [first, last) que tocan la zona y aún no tienen resultado terminal en ella."""
        rows = self.db.execute("SELECT escena, adquisicion, zonas FROM escenas WHERE sensor=? AND fecha_utc>=? "
                               "AND fecha_utc<? AND zonas IS NOT NULL", (sensor, first[:16], last[:16])).fetchall()
        return [row['escena'] for row in rows
                if zone in json.loads(row['zonas']) and zone not in self.zones_done(row['adquisicion'], region)]

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
        """Crea un proceso EN_CURSO y devuelve su id; sus intermedios van en temporary/<id>."""
        with self.db:
            cursor = self.db.execute('''INSERT INTO procesos(escena,aoi,tipo,estado,inicio,validacion,limpieza,
                clave_resultado,clave_correccion,detalle,legado) VALUES(?,?,?,'EN_CURSO',?,'PENDIENTE','PENDIENTE',?,?,?,?)''',
                (scene, config['aoi']['id'], kind, stamp(), result_key, correction_key, canonical({'perfil': config}),
                 int(config['aoi']['id'] in LEGACY_AOIS)))
            process = cursor.lastrowid
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

    def failed_attempts(self, process):
        """Intentos de descarga fallidos registrados para un proceso."""
        return self.db.execute("SELECT count(*) FROM eventos WHERE proceso=? AND tipo='INTENTO_FALLIDO'",
                               (process,)).fetchone()[0]

    def runs(self, state=None, last=None, legacy=False):
        """Lista procesos en orden cronológico (los del AOI vigente o, con `legacy`, los de legado)."""
        rows = self.db.execute('''SELECT p.id, e.fecha_utc, e.satelite, p.tipo, p.estado, p.inicio, p.duracion_min,
            p.descarga_min, p.intentos, p.error, p.l2w, p.archivos, p.escena,
            (SELECT count(*) FROM productos_escena z WHERE z.proceso=p.id AND z.estado='OK') AS zonas_ok
            FROM procesos p LEFT JOIN escenas e USING (escena) WHERE (? IS NULL OR p.estado=?) AND p.legado=?
            ORDER BY p.id DESC LIMIT ?''', (state, state, int(legacy), -1 if last is None else last)).fetchall()
        return [dict(r) for r in reversed(rows)]

    def legacy_count(self):
        """Número de procesos de legado (para avisar que existen sin mezclarlos)."""
        return self.db.execute('SELECT count(*) FROM procesos WHERE legado=1').fetchone()[0]

    # ---------- superimagen ----------

    def record_product(self, scene, zone, aoi, **columns):
        """Crea o reemplaza el resultado de una escena en una zona (una fila por escena, zona y AOI)."""
        columns = {key: canonical(value) if isinstance(value, (dict, list)) else value for key, value in columns.items()}
        columns['fecha_proceso'] = stamp()
        with self.db:
            row = self.db.execute('SELECT id FROM productos_escena WHERE escena=? AND zona=? AND aoi=?',
                                  (scene, zone, aoi)).fetchone()
            if row:
                self.db.execute('UPDATE productos_escena SET '+','.join(f'{k}=?' for k in columns)+' WHERE id=?',
                                (*columns.values(), row['id']))
                return row['id']
            cursor = self.db.execute(f"INSERT INTO productos_escena(escena,zona,aoi,{','.join(columns)}) "
                                     f"VALUES(?,?,?{',?'*len(columns)})", (scene, zone, aoi, *columns.values()))
            return cursor.lastrowid

    def zone_results(self, processes):
        """{estado: (cantidad, bytes)} de los productos por zona creados por los procesos dados."""
        marks = ','.join('?'*len(processes))
        return {row[0]: (row[1], row[2]) for row in self.db.execute(
            f'SELECT estado, count(*), coalesce(sum(bytes),0) FROM productos_escena WHERE proceso IN ({marks}) '
            'GROUP BY estado', list(processes))}

    def products(self, aoi, zone, sensor, first, last):
        """Productos OK de una zona y sensor con fecha en [first, last] (AAAA-MM-DD), por fecha."""
        return [dict(row) for row in self.db.execute(
            '''SELECT * FROM productos_escena WHERE aoi=? AND zona=? AND sensor=? AND estado='OK'
               AND fecha BETWEEN ? AND ? ORDER BY fecha, instante_utc, id''', (aoi, zone, sensor, first, last))]

    def product_dates(self, aoi, sensor, first, last):
        """(zona, fecha) con productos OK del sensor en [first, last]."""
        return [(row['zona'], row['fecha']) for row in self.db.execute(
            '''SELECT DISTINCT zona, fecha FROM productos_escena WHERE aoi=? AND sensor=? AND estado='OK'
               AND fecha BETWEEN ? AND ? ORDER BY zona, fecha''', (aoi, sensor, first, last))]

    def product_sizes(self, sensor):
        """(zona, bytes) de los productos OK de un sensor, para estimar el disco con lo medido."""
        return [(row[0], row[1]) for row in self.db.execute(
            "SELECT zona, bytes FROM productos_escena WHERE sensor=? AND estado='OK' AND bytes", (sensor,))]

    def record_mask(self, zone, sensor, resolution, path, info):
        """Registra la máscara de tierra de una zona, sensor y resolución, con la capa y su versión."""
        path = Path(path).resolve()
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO mascaras VALUES(?,?,?,?,?,?,?,?)',
                            (zone, sensor, resolution, str(path.relative_to(self.storage)), info['capa'],
                             file_hash(path), info.get('tierra_pct'), stamp()))

    def mask(self, zone, sensor, resolution):
        """Fila de la máscara de tierra registrada, o None."""
        row = self.db.execute('SELECT * FROM mascaras WHERE zona=? AND sensor=? AND resolucion_m=?',
                              (zone, sensor, resolution)).fetchone()
        return dict(row) if row else None

    def composite(self, kind, method, aoi, zone, sensor, period):
        """Fila de un compuesto (o mapa diario de sargazo), o None."""
        row = self.db.execute('SELECT * FROM compuestos WHERE tipo=? AND metodo=? AND aoi=? AND zona=? AND sensor=? '
                              'AND periodo=?', (kind, method, aoi, zone, sensor, period)).fetchone()
        return dict(row) if row else None

    def record_composite(self, kind, method, aoi, zone, sensor, period, folder, signature, size, members, detail):
        """Crea o reemplaza un compuesto con su lista de productos de escena (linaje) y devuelve su id."""
        with self.db:
            self.db.execute('DELETE FROM compuestos WHERE tipo=? AND metodo=? AND aoi=? AND zona=? AND sensor=? AND periodo=?',
                            (kind, method, aoi, zone, sensor, period))
            cursor = self.db.execute('''INSERT INTO compuestos(tipo,metodo,aoi,zona,sensor,periodo,carpeta,firma,bytes,
                n_escenas,fecha_proceso,detalle) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (kind, method, aoi, zone, sensor, period, folder, signature, size, len(members), stamp(), canonical(detail)))
            self.db.executemany('INSERT INTO compuesto_escenas VALUES(?,?)', [(cursor.lastrowid, m) for m in members])
        return cursor.lastrowid

    def composite_members(self, composite):
        """Ids de productos de escena que entraron en un compuesto."""
        return [row[0] for row in self.db.execute('SELECT producto FROM compuesto_escenas WHERE compuesto=? '
                                                  'ORDER BY producto', (composite,))]

    def composites(self, kind, aoi, zone, sensor, method=None):
        """Compuestos de un tipo (p. ej. todos los mensuales de una zona y sensor), por periodo."""
        return [dict(row) for row in self.db.execute(
            'SELECT * FROM compuestos WHERE tipo=? AND aoi=? AND zona=? AND sensor=? AND (? IS NULL OR metodo=?) '
            'ORDER BY periodo', (kind, aoi, zone, sensor, method, method))]

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

    def stage_peak(self, stage, family, recent=20):
        """Mayor RSS (bytes) de una etapa exitosa en los últimos `recent` procesos OK de la familia; None sin historial.

        Solo los recientes: si cambia el método de una etapa (p. ej. la descarga), sus picos
        antiguos dejan de pesar.
        """
        values = [m['rss_bytes'] for (detail,) in self.db.execute(
                      "SELECT detalle FROM procesos WHERE estado='OK' AND json_extract(detalle,'$.perfil.family')=? "
                      "ORDER BY id DESC LIMIT ?", (family, recent))
                  for data in [json.loads(detail or '{}')] if data.get('perfil', {}).get('family') == family
                  for m in data.get('metrics', []) if m.get('stage') == stage and m.get('ok') and m.get('rss_bytes')]
        return max(values) if values else None
