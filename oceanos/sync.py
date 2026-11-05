"""Trae a este storage la superimagen producida en otra computadora.

Se pegan en `storage/superimagen/sincronizar/` la carpeta `escenas/` y el `catalog.sqlite` de la
otra computadora, y `oceanos sync` los incorpora:

- **Búsquedas OK** del mismo AOI, para que los meses cuenten como buscados y tengan compuesto.
- **Escenas** que aquí no existían. Una escena que allá quedó sin terminar entra como NUEVA: no se
  pone en la cola, pero deja el mes incompleto hasta que alguien la termine.
- **Productos por zona** (OK, NUBOSA, SIN_DATOS), con su linaje completo y un proceso SINCRONIZADO
  que guarda el proceso de origen. Si aquí ya hay un producto de la misma adquisición y zona, se
  queda el de fecha de proceso más reciente; el otro se borra (fila y carpeta).
- Cada carpeta OK se verifica antes de moverla: están todos los COG de `variables`, GDAL los abre
  y suman los `bytes` del linaje. Si algo no cuadra, ese producto no entra y su carpeta se queda.

Es idempotente: lo ya traído se reconoce por su fecha de proceso y se omite. Si todo entró, se
borran el catálogo pegado y las carpetas vacías; lo que no se reconoció queda y se informa.
Sargazo y compuestos se recalculan después (`cli.derived_products`), sin descargar.
"""
import json
import shutil
import sqlite3
from pathlib import Path
from osgeo import gdal
from .catalog import stamp
from .config import canonical

FOLDER = 'sincronizar'
SOURCE_VERSIONS = (6, 7)
# Estados de escena que se conservan al traerla; los demás (en cola o fallida allá) entran como NUEVA.
KEPT_STATES = ('PROCESADA', 'DISPONIBLE')


def folder(storage):
    """Carpeta donde se pega lo traído de otra computadora."""
    return Path(storage)/'superimagen'/FOLDER


def columns(db, table):
    """Nombres de las columnas de una tabla."""
    return [row[1] for row in db.execute(f'PRAGMA table_info({table})')]


def open_source(path):
    """Abre el catálogo pegado y comprueba su versión."""
    source = sqlite3.connect(path)
    source.row_factory = sqlite3.Row
    version = source.execute('PRAGMA user_version').fetchone()[0]
    if version not in SOURCE_VERSIONS:
        source.close()
        raise ValueError(f'El catálogo pegado es v{version}; sync acepta v6 o v7. Actualice OCEANOS en la otra '
                         'computadora y ejecute allí cualquier comando (p. ej. oceanos status) para migrarlo')
    return source


def insert(db, table, row, skip=('id',), **override):
    """Inserta en `table` las columnas de `row` que existen aquí (salvo `skip`) y devuelve el id."""
    names = [name for name in columns(db, table) if name not in skip and (name in override or name in row.keys())]
    values = [override[name] if name in override else row[name] for name in names]
    cursor = db.execute(f"INSERT INTO {table}({','.join(names)}) VALUES({','.join('?'*len(names))})", values)
    return cursor.lastrowid


def import_searches(catalog, source, aoi):
    """Búsquedas OK del AOI que aquí no estaban (mismo proveedor, sensor, satélites, intervalo y fecha)."""
    added = 0
    with catalog.db:
        for row in source.execute("SELECT * FROM busquedas WHERE aoi=? AND estado='OK'", (aoi,)):
            known = catalog.db.execute('SELECT 1 FROM busquedas WHERE aoi=? AND proveedor=? AND sensor=? AND satelites IS ? '
                                       'AND desde=? AND hasta=? AND fecha=?', (aoi, row['proveedor'], row['sensor'],
                                       row['satelites'], row['desde'], row['hasta'], row['fecha'])).fetchone()
            if not known:
                insert(catalog.db, 'busquedas', row)
                added += 1
    return added


def import_scenes(catalog, source):
    """Escenas que aquí no existían; a una existente solo se le completan las zonas si no las tenía."""
    added = 0
    with catalog.db:
        for row in source.execute('SELECT * FROM escenas'):
            local = catalog.db.execute('SELECT zonas FROM escenas WHERE escena=?', (row['escena'],)).fetchone()
            if local:
                if local['zonas'] is None and row['zonas'] is not None:
                    catalog.db.execute('UPDATE escenas SET zonas=? WHERE escena=?', (row['zonas'], row['escena']))
                continue
            if row['proveedor'] == 'LOCAL' and not source.execute('SELECT 1 FROM productos_escena WHERE escena=?',
                                                                  (row['escena'],)).fetchone():
                continue
            kept = row['estado'] in KEPT_STATES
            insert(catalog.db, 'escenas', row, skip=(), estado=row['estado'] if kept else 'NUEVA',
                   registrada=row['registrada'] if kept else None)
            added += 1
    return added


def check_folder(path, row):
    """Comprueba la carpeta de un producto OK traído; devuelve el motivo si no sirve, o None."""
    if not path.is_dir():
        return 'falta la carpeta'
    total = 0
    for name in json.loads(row['variables'] or '[]'):
        file = path/name
        if not file.is_file():
            return 'falta '+name
        if gdal.Open(str(file)) is None:
            return 'GDAL no abre '+name
        total += file.stat().st_size
    if row['bytes'] is not None and total != row['bytes']:
        return f"los archivos suman {total} bytes y el linaje dice {row['bytes']}"
    return None


def remove_product(catalog, row):
    """Borra un producto local reemplazado: su fila, sus vínculos a compuestos y su carpeta."""
    with catalog.db:
        catalog.db.execute('DELETE FROM compuesto_escenas WHERE producto=?', (row['id'],))
        catalog.db.execute('DELETE FROM productos_escena WHERE id=?', (row['id'],))
    if row['carpeta']:
        path = (catalog.storage/row['carpeta']).resolve()
        if path.is_relative_to((catalog.storage/'superimagen'/'escenas').resolve()) and path.is_dir():
            shutil.rmtree(path)


def process_for(catalog, source, origin, scene, aoi, processes):
    """Proceso SINCRONIZADO local para un proceso de la otra computadora (uno por proceso de origen)."""
    if origin in processes:
        return processes[origin]
    row = source.execute('SELECT * FROM procesos WHERE id=?', (origin,)).fetchone()
    detail = json.loads(row['detalle'] or '{}') if row else {}
    detail['sincronizado'] = {'proceso_origen': origin, 'fecha': stamp()}
    values = {'escena': scene, 'aoi': aoi, 'tipo': 'SINCRONIZADO', 'estado': row['estado'] if row else 'OK',
              'validacion': row['validacion'] if row else 'TECNICA_OK', 'limpieza': 'NO_APLICA',
              'detalle': canonical(detail)}
    with catalog.db:
        if row:
            processes[origin] = insert(catalog.db, 'procesos', row, **values)
        else:
            processes[origin] = catalog.db.execute(
                'INSERT INTO procesos(escena,aoi,tipo,estado,validacion,limpieza,detalle) VALUES(?,?,?,?,?,?,?)',
                tuple(values.values())).lastrowid
    return processes[origin]


def import_product(catalog, source, row, root, aoi, processes, report):
    """Trae un producto por zona; devuelve IMPORTADO, REEMPLAZO, OMITIDO o ERROR."""
    label = f"{row['zona']} {row['sensor']} {row['fecha']} ({row['escena']})"
    acquisition = source.execute('SELECT adquisicion FROM escenas WHERE escena=?', (row['escena'],)).fetchone()
    acquisition = acquisition['adquisicion'] if acquisition else None
    local = [dict(r) for r in catalog.db.execute(
        'SELECT z.* FROM productos_escena z JOIN escenas e USING (escena) WHERE e.adquisicion=? AND z.zona=? AND z.aoi=?',
        (acquisition, row['zona'], aoi))] if acquisition else []
    local += [dict(r) for r in catalog.db.execute('SELECT * FROM productos_escena WHERE escena=? AND zona=? AND aoi=?',
                                                  (row['escena'], row['zona'], aoi)) if r['id'] not in {l['id'] for l in local}]
    origin = root/Path(row['carpeta']).relative_to('superimagen') if row['carpeta'] else None
    if local and max(l['fecha_proceso'] or '' for l in local) >= (row['fecha_proceso'] or ''):
        # Aquí hay uno igual o más nuevo: lo traído sobra.
        if origin and origin.is_dir():
            shutil.rmtree(origin)
        report['omitidos'].append(label)
        return 'OMITIDO'
    if row['estado'] == 'OK':
        problem = check_folder(origin, row)
        if problem:
            report['errores'].append(f'{label}: {problem}')
            return 'ERROR'
    for old in local:
        remove_product(catalog, old)
    process = process_for(catalog, source, row['proceso'], row['escena'], aoi, processes)
    if origin:
        target = catalog.storage/row['carpeta']
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        origin.rename(target)
    with catalog.db:
        insert(catalog.db, 'productos_escena', row, proceso=process)
    (report['reemplazados'] if local else report['importados']).append(label)
    report['sensores'].add(row['sensor'])
    return 'REEMPLAZO' if local else 'IMPORTADO'


def leftovers(root):
    """Borra las carpetas vacías bajo `root` (y `root` si queda vacía); devuelve lo que sigue ahí."""
    for path in sorted((p for p in root.rglob('*') if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(path.iterdir()):
            path.rmdir()
    remaining = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_file())
    if not remaining and root.is_dir() and not any(root.iterdir()):
        root.rmdir()
    return remaining


def sync(catalog, aoi):
    """Incorpora lo pegado en storage/superimagen/sincronizar y devuelve un informe.

    `aoi` es el id del perfil vigente: productos y búsquedas de otro AOI no se traen.
    """
    root = folder(catalog.storage)
    path = root/'catalog.sqlite'
    if not path.is_file():
        raise ValueError(f'Falta {path.relative_to(catalog.storage)}: pegue ahí el catalog.sqlite y la carpeta '
                         'escenas/ de superimagen de la otra computadora')
    report = {'importados': [], 'reemplazados': [], 'omitidos': [], 'errores': [], 'otro_aoi': 0,
              'busquedas': 0, 'escenas': 0, 'sensores': set(), 'restos': [], 'catalogo_borrado': False}
    source = open_source(path)
    try:
        report['busquedas'] = import_searches(catalog, source, aoi)
        report['escenas'] = import_scenes(catalog, source)
        report['otro_aoi'] = source.execute('SELECT count(*) FROM productos_escena WHERE aoi IS NOT ?', (aoi,)).fetchone()[0]
        processes = {}
        for row in source.execute('SELECT * FROM productos_escena WHERE aoi=? ORDER BY id', (aoi,)).fetchall():
            import_product(catalog, source, row, root, aoi, processes, report)
    finally:
        source.close()
    catalog.event('SINCRONIZACION', f"{len(report['importados'])} productos nuevos, {len(report['reemplazados'])} "
                                    f"reemplazados, {len(report['omitidos'])} omitidos, {len(report['errores'])} con "
                                    f"errores; {report['busquedas']} búsquedas y {report['escenas']} escenas")
    if not report['errores']:
        # Todo entró: el catálogo pegado ya no hace falta (con sus archivos WAL si los trajo).
        for name in ('catalog.sqlite', 'catalog.sqlite-wal', 'catalog.sqlite-shm', 'catalog.sqlite-journal'):
            (root/name).unlink(missing_ok=True)
        report['catalogo_borrado'] = True
    report['restos'] = leftovers(root)
    return report
