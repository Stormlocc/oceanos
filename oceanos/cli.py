"""Interfaz de línea de comandos; ejecutar dentro del entorno ACOLITE de WSL."""
import argparse
import json
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path
from .catalog import VERSION, Catalog
from .config import ROOT, ACOLITE, PLATFORMS, PROFILE, canonical, exclusive, file_hash, instant, profile, profile_sensors
from .escenas import SENSOR_TAG
from .native import prepare, scene_identity, eligible
from .pipeline import (DISK_MARGIN, Pipeline, cleanup, disk_free, explain, product_estimate, recover,
                       superimagen_bytes)
from .progress import Progress, size, duration
from .resources import plan
from .sync import sync

SATELLITES = {platform: family for family, platforms in PLATFORMS.items() for platform in platforms}
STATES = ['EN_CURSO', 'OK', 'OMITIDO', 'FALLIDO', 'INTERRUMPIDO', 'IMPORTADO']
RESULTS = ['OK', 'DISPONIBLE', 'FALLIDA', 'PENDIENTE']
LOCAL_FORMATS = {'sentinel2': 'SAFE', 'landsat': 'TAR', 'olci': 'SEN3'}
DATE = 'AAAA-MM-DD[THH:MM:SSZ]'


def date_text(value):
    """Valida una fecha UTC ISO 8601 y la devuelve sin cambios."""
    try:
        instant(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha inválida '{value}': use {DATE}, p. ej. 2026-08-01 o 2026-08-01T00:00:00Z") from None
    return value


def name_list(value):
    """Lista separada por comas (productos o zonas); el perfil valida cada nombre."""
    items = [item.strip() for item in value.split(',')]
    if not all(items):
        raise argparse.ArgumentTypeError('lista vacía o con elementos vacíos')
    return items


def satellite_list(value):
    """Valida satélites separados por coma; acepta minúsculas y LC08/LC09."""
    items = [item.strip().upper().replace('LC0', 'L') for item in value.split(',')]
    unknown = [item for item in items if item not in SATELLITES]
    if unknown:
        raise argparse.ArgumentTypeError(f"satélite desconocido {', '.join(unknown)}; opciones: "
                                         "S2A, S2B, S2C (sentinel2), L8, L9 (landsat), S3A, S3B (olci)")
    return list(dict.fromkeys(items))


def workers_count(value):
    """Valida --trabajadores: entero mayor o igual a 1."""
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError(f"valor inválido '{value}': use un entero ≥ 1 (1 = una escena a la vez)")
    return number


class Formatter(argparse.RawDescriptionHelpFormatter):
    """Ayuda en español que respeta los saltos de línea de descripciones y ejemplos."""
    def add_usage(self, usage, actions, groups, prefix=None):
        """Usa 'uso:' en lugar de 'usage:'."""
        return super().add_usage(usage, actions, groups, 'uso: ' if prefix is None else prefix)


def spanish(parser):
    """Traduce los títulos y la opción -h de un parser de argparse."""
    parser._positionals.title = 'argumentos'
    parser._optionals.title = 'opciones'
    parser.add_argument('-h', '--help', action='help', help='mostrar esta ayuda y salir')
    return parser


def selection(parser, top=False):
    """Agrega --sensor, --satelite, --zona, --start y --end; en subcomandos no pisan lo dado antes del comando."""
    hidden = {} if top else {'default': argparse.SUPPRESS}
    group = parser.add_argument_group('selección' + ('' if top else ' (también válidas antes del comando)'))
    group.add_argument('--sensor', choices=list(PLATFORMS), **hidden,
                       help='solo ese sensor. Por defecto todos los del perfil, en orden: sentinel2, landsat, olci')
    group.add_argument('--satelite', type=satellite_list, metavar='SAT[,SAT]', **hidden,
                       help='solo esos satélites: S2A, S2B, S2C, L8, L9, S3A, S3B, separados por coma')
    group.add_argument('--zona', type=name_list, metavar='ZONA[,ZONA]', **hidden,
                       help='solo esas zonas: mayaguez_cabo_rojo, la_parguera_guanica, ponce_guayanilla, fajardo_culebra')
    group.add_argument('--start', type=date_text, metavar=DATE, **hidden,
                       help='inicio UTC incluido. Por defecto el del perfil')
    group.add_argument('--end', type=date_text, metavar=DATE, **hidden,
                       help='fin UTC EXCLUIDO (para incluir el 14 use 2026-08-15). Por defecto el del perfil')


def parser():
    """Define los argumentos globales y los subcomandos del CLI."""
    options = {'formatter_class': Formatter, 'add_help': False}
    if sys.version_info >= (3, 14):
        # Sugiere el valor correcto ante un error de escritura (p. ej. 'serch' -> 'search').
        options['suggest_on_error'] = True
    result = spanish(argparse.ArgumentParser(prog='oceanos', description=(
        'Pipeline OCEANOS: superimagen Water2Coast con ACOLITE nativo y catálogo SQLite local.\n\n'
        'Uso habitual:\n'
        '  oceanos prepare                       # una vez: verificar ACOLITE\n'
        '  oceanos run --plan                    # ver qué se descargaría y cuánto disco ocuparía\n'
        '  oceanos run                           # todo: buscar, descargar, ACOLITE, escenas, sargazo, compuestos\n'
        '  oceanos superimagen                   # productos por zona y presupuesto de disco\n'
        '  oceanos reporte                       # resultado por escena\n\n'
        'Ayuda de cada comando: oceanos <comando> -h'), **options))
    general = result.add_argument_group('rutas y perfil')
    general.add_argument('--storage', type=Path, default=ROOT/'storage', metavar='CARPETA',
                         help='catálogo, temporales y superimagen. Por defecto: storage/')
    general.add_argument('--acolite', type=Path, default=ACOLITE, metavar='CARPETA',
                         help=f'instalación de ACOLITE. Por defecto: {ACOLITE}')
    general.add_argument('--profile', type=Path, default=PROFILE, metavar='CARPETA',
                         help='carpeta del perfil (project.yaml y un YAML por sensor). Por defecto: config/aoi/water2coast_v1')
    general.add_argument('--products', type=name_list, metavar='PROD[,PROD]',
                         help='solo esos productos del perfil (l2w_parameters de ACOLITE). Por defecto todos')
    selection(result, top=True)
    commands = result.add_subparsers(dest='command', required=True, metavar='COMANDO', title='comandos')

    def command(name, summary, description='', examples='', hidden=False):
        """Crea un subcomando con ayuda en español y ejemplos; `hidden` lo omite de `oceanos -h`."""
        listed = {} if hidden else {'help': summary}
        sub = commands.add_parser(name, **listed, description=summary + ('\n\n'+description if description else ''),
                                  epilog=('ejemplos:\n'+examples) if examples else None, **options)
        return spanish(sub)

    command('prepare', 'Verificar la revisión de ACOLITE y aplicar el parche de catálogo', examples='  oceanos prepare')
    run = command('run', 'Todo en uno: buscar, descargar, ACOLITE, escenas, sargazo diario y compuestos mensuales',
        'Por cada sensor: máscaras de tierra → búsqueda y registro de escenas nuevas → descarga →\n'
        'ACOLITE por zona → COG en superimagen/escenas (se borran crudo, L1R, L2R y L2W) → sargazo\n'
        'diario → compuestos de los meses completos (y sus estaciones y años). Se puede cortar y\n'
        'repetir: lo terminado no se descarga ni se recalcula otra vez.\n\n'
        'Antes de descargar muestra cuántas escenas y cuántos GB, y la estimación de disco de la\n'
        'superimagen frente a su presupuesto. --plan se detiene ahí.\n\n'
        'Paralelo: varias escenas a la vez según CPU, RAM y disco del equipo (OCEANOS_CPUS,\n'
        'OCEANOS_RAM_GB, OCEANOS_DESCARGAS los fijan a mano; CDSE admite 4 descargas a la vez).',
        '  oceanos run --plan --start 2025-12-01 --end 2026-02-01\n'
        '  oceanos run --start 2025-12-01 --end 2026-02-01\n'
        '  oceanos run --sensor landsat --zona fajardo_culebra\n'
        '  oceanos run --escena 20251216\n'
        '  oceanos run --sensor sentinel2 --source /ruta/escena.zip --scene S2B_MSIL1C_..._T19QGV_....SAFE')
    selection(run)
    run.add_argument('--plan', action='store_true', help='buscar y mostrar qué se descargaría, sin registrar ni descargar')
    local = run.add_argument_group('una sola escena')
    local.add_argument('--escena', dest='version', metavar='ESCENA',
                       help='procesar solo esta escena (nombre o fragmento único), sin buscar')
    local.add_argument('--source', type=Path, metavar='ARCHIVO', help='ZIP (S2, OLCI) o TAR (Landsat) local; requiere --scene')
    local.add_argument('--scene', metavar='NOMBRE', help='nombre nativo de la escena del archivo local')
    run.add_argument('--force', action='store_true', help='reprocesar zonas que ya tienen resultado')
    run.add_argument('--trabajadores', type=workers_count, metavar='N',
                     help='escenas a la vez (1 = secuencial). Por defecto según el equipo')
    search = command('search', 'Consultar el proveedor sin descargar (CDSE para S2 y OLCI, USGS para Landsat)',
        'Muestra fecha, satélite, tile, tamaño L1, nubosidad publicada, zonas que toca y estado:\n'
        '  NUEVA       aún no en cola · PENDIENTE en cola · FALLIDA se reintenta en el próximo run\n'
        '  PROCESADA   sus zonas tienen resultado · DISPONIBLE su adquisición ya estaba completa',
        '  oceanos search --sensor landsat\n'
        '  oceanos search --registrar 20251216        # dejar en cola solo esa')
    selection(search)
    search.add_argument('--registrar', nargs='*', metavar='ESCENA',
                        help='dejar en la cola: sin nombres, todas las NUEVAS; con nombres o fragmentos únicos, solo esas')
    search.add_argument('--json', action='store_true', help='imprimir solo los nombres de las escenas en JSON')
    for name, summary, example in (
            ('mascara', 'Crear las máscaras de tierra (ESA WorldCover) de cada zona y sensor', '  oceanos mascara'),
            ('sargazo', 'Recalcular los mapas diarios de sargazo desde superimagen/escenas (sin descargar)',
             '  oceanos sargazo --sensor sentinel2 --start 2025-12-01 --end 2026-02-01'),
            ('componer', 'Recalcular compuestos mensuales, estacionales y anuales de los meses completos (sin descargar)',
             '  oceanos componer --zona fajardo_culebra')):
        selection(command(name, summary, examples=example))
    command('superimagen', 'Productos por zona y sensor, compuestos y disco frente al presupuesto (sin red)',
            examples='  oceanos superimagen')
    status = command('status', 'Procesos desde SQLite (sin ACOLITE ni red)',
        examples='  oceanos status --ultimas 5\n  oceanos status --estado FALLIDO\n  oceanos status 7\n  oceanos status --legado')
    status.add_argument('run', nargs='?', metavar='PROCESO', help='número de proceso: detalle con métricas y eventos')
    status.add_argument('--ultimas', type=int, metavar='N', help='solo los N procesos más recientes')
    status.add_argument('--estado', choices=STATES, metavar='ESTADO', help='filtrar por estado: '+', '.join(STATES))
    status.add_argument('--legado', action='store_true', help='procesos de AOI anteriores (lapargera_v1), aparte')
    report = command('reporte', 'Resultado por escena con el de cada zona y el motivo de las fallidas (sin red)',
        '--csv guarda la misma tabla. --legado lista los L1R/L2W de AOI anteriores, que se conservan\n'
        'pero no entran a la superimagen.',
        '  oceanos reporte\n  oceanos reporte --resultado FALLIDA\n  oceanos reporte --sensor landsat --csv reporte.csv\n'
        '  oceanos reporte --legado')
    report.add_argument('--resultado', choices=RESULTS, metavar='RESULTADO', help='filtrar: '+', '.join(RESULTS))
    report.add_argument('--csv', type=Path, metavar='ARCHIVO', help='guardar el reporte en CSV')
    report.add_argument('--sensor', choices=list(PLATFORMS), help='solo ese sensor')
    report.add_argument('--legado', action='store_true', help='listar el legado en vez de la superimagen')
    queue = command('cola', 'Ver la cola de descargas (sin red)',
        examples='  oceanos cola\n  oceanos cola --quitar 20260116 20260205')
    queue.add_argument('--quitar', nargs='+', metavar='ESCENA', help='retirar de la cola escenas no procesadas')
    imports = command('sync', 'Registrar como legado L1R/L2W copiados a mano a una carpeta de storage',
        'Se conservan y se listan con --legado; no cuentan para la superimagen ni para la cola.',
        '  oceanos sync storage/importados/pc2 --hash')
    imports.add_argument('carpeta', nargs='?', type=Path, metavar='CARPETA',
                         help='carpeta dentro de storage. Por defecto: storage/importados')
    imports.add_argument('--hash', action='store_true', help='calcular también el SHA-256 de cada archivo (lento)')
    command('recover', 'Registrar interrupciones y limpiar lo parcial (automático al iniciar run y search)',
            examples='  oceanos recover')
    clean = command('cleanup', 'Evaluar la limpieza de temporales de un proceso', examples='  oceanos cleanup 7', hidden=True)
    clean.add_argument('run', type=int, metavar='PROCESO', help='número de proceso (ver status)')
    return result


def sensors_for(args):
    """Sensores a procesar: --sensor, los de --satelite o todos los del perfil."""
    if args.sensor:
        return [args.sensor]
    if args.satelite:
        return list(dict.fromkeys(SATELLITES[s] for s in args.satelite))
    return profile_sensors(args.profile)


def load_profiles(args):
    """Un perfil por sensor elegido, con productos, intervalo, satélites y zonas de la línea de comandos."""
    configs = []
    for sensor in sensors_for(args):
        satellites = [s for s in args.satelite or [] if SATELLITES[s] == sensor] or None
        if args.satelite and not satellites:
            raise ValueError(f"--satelite {','.join(args.satelite)} no es del sensor {sensor}")
        configs.append(profile(args.profile, sensor, args.products, args.start, args.end, satellites, args.zona))
    return configs


def table(rows, columns):
    """Imprime filas (dicts) como tabla de texto alineada con las columnas indicadas."""
    text = lambda value: '—' if value is None else str(value)
    widths = [max(len(title), *(len(text(row[key])) for row in rows)) for title, key in columns]
    print('  '.join(title.ljust(width) for (title, _), width in zip(columns, widths)))
    for row in rows:
        print('  '.join(text(row[key]).ljust(width) for (_, key), width in zip(columns, widths)))


def scene_rows(catalog, scenes, config):
    """Filas de las escenas encontradas con su estado al día (DISPONIBLE si su adquisición ya está completa)."""
    done = catalog.completed(config['aoi']['id'], config['zones'])
    rows = []
    for scene in scenes:
        row = dict(catalog.db.execute('SELECT * FROM escenas WHERE escena=?', (scene,)).fetchone())
        if row['adquisicion'] in done and row['estado'] in ('NUEVA', 'PENDIENTE', 'FALLIDA'):
            catalog.scene_state(scene, 'DISPONIBLE')
            row['estado'] = 'DISPONIBLE'
        row['tamano'] = f"{row['tamano_mb']:,.1f} MB" if row['tamano_mb'] else 'no informado'
        row['zonas'] = ','.join(json.loads(row['zonas'] or '[]'))
        rows.append(row)
    return sorted(rows, key=lambda row: row['fecha_utc'])


def show_versions(rows):
    """Tabla de search y totales por estado."""
    if rows:
        table(rows, [('FECHA (UTC)', 'fecha_utc'), ('SAT', 'satelite'), ('TILE', 'tile'), ('TAMAÑO L1', 'tamano'),
                     ('NUBES %', 'nubosidad'), ('ZONAS', 'zonas'), ('ESTADO', 'estado'), ('ESCENA', 'escena')])
    states = Counter(row['estado'] for row in rows)
    print(f"\n{len(rows)} escenas · " + ' · '.join(f'{count} {state}' for state, count in sorted(states.items())))


COMPLETENESS = {
    'COMPLETE': 'completa: el proveedor devolvió todas las escenas que coinciden con la búsqueda',
    'INCOMPLETE': 'INCOMPLETA: el proveedor tiene más coincidencias que las devueltas (la paginación se '
                  'cortó); repita la búsqueda o acote --start/--end',
    'UNKNOWN': 'desconocida: el proveedor no informó el total de coincidencias, no se puede asegurar que estén todas'}


def show_query(report):
    """Explica la consulta al proveedor: devueltas, completitud, descartadas por el perfil y tamaños."""
    if not report:
        return
    counts = report.get('provider_counts') or {}
    total = f" de {counts['totalHits']} coincidencias" if counts.get('totalHits') is not None else ''
    print(f"Consulta {report['provider']}: {report.get('returned', report['count'])} escenas devueltas{total}, "
          f"{report['count']} cumplen el perfil. Completitud "
          + COMPLETENESS.get(report['completeness'], report['completeness'])+'.')
    excluded = report.get('excluded_by_profile') or []
    if excluded:
        reasons = Counter(item['reason'] for item in excluded)
        print(f'Descartadas por el perfil ({len(excluded)}): '+'; '.join(f'{n} por {why}' for why, n in reasons.items()))
    status, _, missing = report.get('sizes', 'OK').partition(';FALTAN:')
    if status.startswith('NO_DISPONIBLE'):
        print(f"Tamaños: USGS no los entregó ({status.split(':', 1)[1]}). La descarga no depende de esto.")
    if missing:
        print(f'  {missing} escenas quedaron sin tamaño informado.')


def show_estimate(catalog, config, rows):
    """Lo que se descargaría y el disco estimado de la superimagen; avisa si pasa del presupuesto."""
    queued = [row for row in rows if row['estado'] in ('NUEVA', 'PENDIENTE', 'FALLIDA')]
    measured = catalog.product_sizes(SENSOR_TAG[config['family']])
    zones = [zone for row in queued for zone in row['zonas'].split(',') if zone in config['zones']]
    products = sum(product_estimate(config, zone, measured) for zone in zones)
    used = superimagen_bytes(catalog.storage)
    expected = used+products
    basis = f'medido en {len(measured)} producto(s)' if measured else 'sin mediciones todavía'
    print(f"Por descargar: {len(queued)} escenas ({size(sum((r['tamano_mb'] or 0)*1e6 for r in queued))} de L1, "
          'se borran al exportar) · '
          f"{len(zones)} productos de zona, ~{size(products)} ({basis}) · superimagen {size(used)} → ~{size(expected)} "
          f"de {size(config['superimagen_budget'])}")
    if expected > config['superimagen_budget']:
        print('AVISO: la estimación pasa el presupuesto de la superimagen; la exportación se detendrá al alcanzarlo '
              '(PRESUPUESTO_SUPERIMAGEN). Acote --start/--end o --zona.')
    return queued


def register(catalog, rows, selected, config):
    """Pone en la cola las escenas elegidas (todas las NUEVAS y FALLIDAS si no se nombra ninguna)."""
    if selected:
        wanted = {catalog.resolve_scene(text) for text in selected}
        unknown = wanted - {row['escena'] for row in rows}
        if unknown:
            raise ValueError('Escenas fuera de esta búsqueda: '+', '.join(sorted(unknown)))
        chosen = [row['escena'] for row in rows if row['escena'] in wanted]
    else:
        chosen = [row['escena'] for row in rows if row['estado'] in ('NUEVA', 'FALLIDA')]
    queued, refused = catalog.enqueue(chosen, catalog.completed(config['aoi']['id'], config['zones']))
    for scene, why in refused.items():
        print(f'  omitida {scene} — {why}')
    print(f'Registradas {len(queued)} escenas en la cola.')
    return queued


def show_queue(catalog):
    """Tabla de la cola de descargas."""
    items = catalog.queue()
    if not items:
        print("Cola vacía. 'oceanos run' busca y registra las escenas nuevas.")
        return
    table(items, [('FECHA (UTC)', 'fecha_utc'), ('SAT', 'satelite'), ('TAMAÑO MB', 'tamano_mb'), ('ESTADO', 'estado'),
                  ('PROCESOS', 'procesos'), ('ÚLTIMO', 'ultimo'), ('REGISTRADA', 'registrada'), ('ESCENA', 'escena')])
    print('\n'+' · '.join(f'{state}: {count}' for state, count in sorted(Counter(i['estado'] for i in items).items())))


def write_csv(path, rows, columns):
    """Guarda filas en CSV con los títulos de las columnas."""
    import csv
    with Path(path).open('w', newline='', encoding='utf-8') as stream:
        writer = csv.writer(stream)
        writer.writerow([title for title, _ in columns])
        writer.writerows([['' if row[key] is None else row[key] for _, key in columns] for row in rows])
    print(f'CSV guardado en {path}')


def show_report(catalog, result=None, csv_path=None, sensor=None):
    """Tabla por escena (resultado, zonas, motivo) y totales; con `csv_path`, también en CSV."""
    rows = [row for row in catalog.report(sensor) if result is None or row['resultado'] == result]
    for row in rows:
        failed = row['resultado'] in ('FALLIDA', 'PENDIENTE') and row['error']
        row['motivo'] = explain(row['error']) if failed else ''
        row['ultimo'] = row['fin'] or ''
    columns = [('FECHA (UTC)', 'fecha_utc'), ('SAT', 'satelite'), ('TILE', 'tile'), ('RESULTADO', 'resultado'),
               ('ZONAS', 'zonas'), ('INTENTOS', 'intentos'), ('MOTIVO', 'motivo'), ('ÚLTIMO', 'ultimo'), ('ESCENA', 'escena')]
    if not rows:
        print('Sin escenas trabajadas' + (f' con resultado {result}' if result else '') + '.')
    else:
        table(rows, columns)
        counts = Counter(row['resultado'] for row in rows)
        print('\n' + ' · '.join(f'{name}: {counts[name]}' for name in RESULTS if name in counts))
        if counts.get('FALLIDA'):
            print("Las FALLIDA siguen en la cola: 'oceanos run' las reintenta ('oceanos cola --quitar ESCENA' para descartarlas).")
    legacy = catalog.legacy_count()
    if legacy:
        print(f"Legado: {legacy} procesos de AOI anteriores, aparte ('oceanos reporte --legado').")
    if csv_path:
        write_csv(csv_path, rows, columns)


def show_legacy(catalog, csv_path=None):
    """Procesos de legado (AOI anteriores): se conservan, no entran a la superimagen."""
    rows = catalog.legacy()
    columns = [('ID', 'id'), ('AOI', 'aoi'), ('FECHA (UTC)', 'fecha_utc'), ('SAT', 'satelite'), ('TIPO', 'tipo'),
               ('ESTADO', 'estado'), ('L2W', 'l2w'), ('ESCENA', 'escena')]
    if not rows:
        print('Sin procesos de legado.')
        return
    table(rows, columns)
    print(f'\n{len(rows)} procesos de legado: se conservan y nunca entran a la superimagen, la cola ni el "ya lo tenemos".')
    if csv_path:
        write_csv(csv_path, rows, columns)


def show_runs(rows):
    """Tabla de procesos para status."""
    if not rows:
        print('Sin procesos registrados.')
        return
    table(rows, [('ID', 'id'), ('FECHA ESCENA', 'fecha_utc'), ('SAT', 'satelite'), ('TIPO', 'tipo'), ('ESTADO', 'estado'),
                 ('INICIO', 'inicio'), ('MIN', 'duracion_min'), ('DESCARGA MIN', 'descarga_min'), ('INTENTOS', 'intentos'),
                 ('ZONAS OK', 'zonas_ok'), ('ERROR', 'error')])


def show_detail(row):
    """Detalle de un proceso para `status N`."""
    events, metrics = row.pop('eventos'), row.pop('metricas')
    for key, value in row.items():
        if value is not None:
            print(f'{key:17} {value}')
    if metrics:
        print('etapas           ' + ' · '.join(f"{m['stage']} {duration(m['seconds'])}{'' if m['ok'] else ' (falló)'}"
                                               for m in metrics))
    print('eventos:')
    for event in events:
        print('  '+event)


def show_superimagen(catalog, budget):
    """Productos por zona, sensor y estado, compuestos y disco frente al presupuesto."""
    rows = [dict(row) for row in catalog.db.execute('SELECT * FROM v_superimagen ORDER BY zona, sensor, estado')]
    if rows:
        table(rows, [('ZONA', 'zona'), ('SENSOR', 'sensor'), ('ESTADO', 'estado'), ('ESCENAS', 'escenas'), ('GB', 'gb'),
                     ('DESDE', 'desde'), ('HASTA', 'hasta')])
    else:
        print('Sin productos de escena todavía.')
    made = Counter((row['tipo'], row['sensor']) for row in catalog.db.execute('SELECT tipo, sensor FROM compuestos'))
    if made:
        print('Compuestos: ' + ' · '.join(f'{kind} {sensor} {count}' for (kind, sensor), count in sorted(made.items())))
    print(f'Disco de la superimagen: {size(superimagen_bytes(catalog.storage))} de {size(budget)}')


def show_summary(catalog, result):
    """Resumen al terminar el lote: procesos, tiempos, descarga y productos por zona."""
    rows = [catalog.process(run) for run in result['runs']]
    states = Counter(row['estado'] for row in rows)
    downloaded = [row for row in rows if row['descarga_min']]
    seconds = sum(row['descarga_min']*60 for row in downloaded)
    volume = sum((row['descarga_mb'] or 0)*1e6 for row in downloaded)
    print('\n══ Resumen del lote ══')
    print(f"Escenas: {len(rows)} · " + ' · '.join(f'{state} {count}' for state, count in sorted(states.items()))
          + f" · fallidas {len(result['failed'])}")
    print(f"Tiempo total: {duration(result['seconds'])} · descarga {duration(seconds)} ({size(volume)}"
          + (f", {size(volume/seconds)}/s promedio)" if seconds else ')'))
    if rows:
        zones = catalog.zone_results([row['id'] for row in rows])
        print('Zonas: ' + ' · '.join(f'{state} {count}' + (f' ({size(volume)})' if volume else '')
                                     for state, (count, volume) in sorted(zones.items())))


def mask_fetch():
    """Descarga de tiles WorldCover en streaming, solo desde el bucket público de ESA."""
    import requests
    from .mascara import WORLDCOVER_HOST
    from .native import fetch
    session = requests.Session()
    return lambda url, target: fetch(session, url, Path(target), WORLDCOVER_HOST)


def ensure_masks(catalog, config):
    """Crea las máscaras de tierra que falten para el sensor del perfil."""
    from .mascara import ensure
    record = lambda zone, path, info: catalog.record_mask(zone, SENSOR_TAG[config['family']], config['resolution'], path, info)
    return ensure(catalog.storage, config, mask_fetch(), record)


def period_end(config):
    """Último día (AAAA-MM-DD) incluido en el intervalo del perfil."""
    return (instant(config['end'])-timedelta(seconds=1)).date().isoformat()


def derived_products(catalog, config):
    """Sargazo diario y compuestos de los meses completos, sin descargar nada; imprime lo hecho."""
    from . import componer, sargazo
    zones = list(config['zones'])
    if any(product == 'fai' for product in config['products']):
        made = sargazo.update(catalog, config, zones, config['start'][:10], period_end(config))
        print(f"Sargazo diario {config['family']}: " + (' · '.join(f'{k} {v}' for k, v in sorted(made.items())) or 'sin días'))
    made = componer.update(catalog, config, zones)
    print(f"Compuestos {config['family']}: " + (' · '.join(f'{k} {v}' for k, v in sorted(made.items()))
                                               or 'ningún mes completo todavía'))


def local_source(catalog, config, args):
    """Fuente de un archivo local (--source/--scene), registrada si la escena no se conocía."""
    if not args.scene or not args.source.is_file():
        raise ValueError('Se requiere archivo existente y --scene')
    source = {'provider': 'LOCAL', 'product': args.scene, 'format': LOCAL_FORMATS[config['family']],
              'local': str(args.source.resolve()), 'sha256': file_hash(args.source),
              'identity': scene_identity(args.scene), 'metadata': {'identity_origin': 'nombre_del_producto'}}
    if not eligible(source, config):
        raise ValueError('Escena fuera del sensor, intervalo o tile/path/row del perfil')
    if not catalog.db.execute('SELECT 1 FROM escenas WHERE escena=?', (args.scene,)).fetchone():
        catalog.upsert_scene(source, seen=False)
    return source


def queue_for_run(catalog, config, pipeline, args):
    """Escenas que procesa `run`: la pedida, o búsqueda + registro de lo nuevo + cola. None con --plan."""
    if args.version:
        return [catalog.resolve_scene(args.version)]
    rows = scene_rows(catalog, pipeline.search(), config)
    if args.plan:
        # Antes de bajar, la lista completa: qué se descargaría (NUEVA/PENDIENTE/FALLIDA) y qué ya está.
        show_versions(rows)
    show_query(pipeline.last_query)
    show_estimate(catalog, config, rows)
    if args.plan:
        return None
    register(catalog, rows, None, config)
    scenes, outside, available, deferred = catalog.pending(config, force=args.force)
    if available:
        print(f'{len(available)} en cola ya estaban completas; marcadas DISPONIBLE.')
    if deferred:
        print(f'{len(deferred)} repiten la adquisición de otra en este lote; esperan al siguiente run.')
    if outside:
        print(f'{len(outside)} en cola quedan fuera del perfil/intervalo actual y se conservan pendientes.')
    return scenes


def run_sensor(catalog, config, args):
    """`run` para un sensor; devuelve el número de escenas fallidas."""
    print(f"\n══ {config['family']} · {config['start'][:10]} → {config['end'][:10]} · zonas: {', '.join(config['zones'])} ══")
    if not args.plan:
        ensure_masks(catalog, config)
    pipeline = Pipeline(catalog, config, args.acolite, progress=Progress())
    if args.source:
        pipeline.run(args.scene, source=local_source(catalog, config, args), force=args.force)
        derived_products(catalog, config)
        return 0
    scenes = queue_for_run(catalog, config, pipeline, args)
    if scenes is None:
        return 0
    failed = []
    if scenes:
        print(f'Escenas por procesar: {len(scenes)}')
        if len(scenes) > 1 and args.trabajadores != 1:
            # Disco para escenas en curso: lo libre del presupuesto de temporales, sin pasar del disco real.
            free = min(config['budget']-pipeline.used(), disk_free(catalog.storage)-DISK_MARGIN)
            pipeline.resources = plan(catalog, config, free, args.trabajadores, acolite=args.acolite)
            pipeline.resources.workers = min(pipeline.resources.workers, len(scenes))
            print(pipeline.resources.describe())
        result = pipeline.batch(scenes, force=args.force)
        show_summary(catalog, result)
        failed = result['failed']
    derived_products(catalog, config)
    return len(failed)


def catalog_notice(catalog):
    """Explica una migración o un catálogo nuevo al abrirlo."""
    if catalog.migrated:
        legacy = (f" {catalog.legacy_count()} procesos de lapargera_v1 quedan como legado ('oceanos reporte --legado')."
                  if catalog.migrated_from == 4 else '')
        print(f'Catálogo v{catalog.migrated_from} migrado a v{VERSION} '
              f'(respaldo: {catalog.backup.relative_to(catalog.storage)}).'+legacy)
    elif catalog.backup:
        print(f'Catálogo anterior guardado como {catalog.backup.relative_to(catalog.storage)}; se empezó uno nuevo.')


def offline_command(catalog, args):
    """Comandos que solo leen o mantienen el catálogo; devuelve el código de salida o None si no aplica."""
    if args.command == 'status':
        if args.run:
            show_detail(catalog.run_detail(args.run))
        else:
            show_runs(catalog.runs(args.estado, args.ultimas, legacy=args.legado))
        return 0
    if args.command == 'recover':
        result = recover(catalog)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result['limpieza_fallida'] else 0
    if args.command == 'cleanup':
        print(cleanup(catalog, args.run))
        return 0
    if args.command == 'reporte':
        if args.legado:
            show_legacy(catalog, args.csv)
        else:
            show_report(catalog, args.resultado, args.csv, args.sensor)
        return 0
    if args.command == 'cola':
        for text in args.quitar or []:
            catalog.dequeue(catalog.resolve_scene(text))
        show_queue(catalog)
        return 0
    if args.command == 'sync':
        report = sync(catalog, args.carpeta or args.storage/'importados', hashed=args.hash)
        for key in ('reaparecidos', 'desaparecidos', 'no_reconocidos', 'duplicados'):
            for name in report[key]:
                print(f'  {key}: {name}')
        print(f"Importados como legado {len(report['importados'])} archivos · ya registrados {report['ya_registrados']}")
        return 0
    return None


def profile_command(catalog, args):
    """Comandos que usan el perfil (uno o varios sensores); devuelve el código de salida."""
    configs = load_profiles(args)
    if args.command == 'superimagen':
        show_superimagen(catalog, configs[0]['superimagen_budget'])
        return 0
    if args.command in ('search', 'run'):
        recovered = recover(catalog)
        if recovered['limpiados'] or recovered['limpieza_fallida']:
            print('Recuperación:', json.dumps(recovered, ensure_ascii=False))
    if args.source and len(configs) != 1:
        raise ValueError('--source requiere --sensor')
    failed = 0
    for config in configs:
        if args.command == 'mascara':
            for zone, path in ensure_masks(catalog, config).items():
                print(f'{zone}: {path.relative_to(catalog.storage)}')
        elif args.command == 'sargazo':
            from . import sargazo
            made = sargazo.update(catalog, config, list(config['zones']), config['start'][:10], period_end(config))
            print(f"{config['family']}: {made or 'sin días con FAI'}")
        elif args.command == 'componer':
            from . import componer
            print(f"{config['family']}: {componer.update(catalog, config, list(config['zones'])) or 'ningún mes completo'}")
        elif args.command == 'search':
            pipeline = Pipeline(catalog, config, args.acolite)
            scenes = pipeline.search()
            if args.json:
                print(canonical({'escenas': scenes}))
                continue
            rows = scene_rows(catalog, scenes, config)
            show_versions(rows)
            show_query(pipeline.last_query)
            if args.registrar is not None:
                register(catalog, rows, args.registrar, config)
        else:
            failed += run_sensor(catalog, config, args)
    return 1 if failed else 0


def main(argv=None):
    """Ejecuta un subcomando bajo el bloqueo exclusivo del catálogo y devuelve el código de salida."""
    args = parser().parse_args(argv)
    for name in ('source', 'plan', 'version', 'force', 'trabajadores', 'registrar', 'json', 'legado'):
        setattr(args, name, getattr(args, name, None))
    try:
        with exclusive(args.storage):
            if args.command == 'prepare':
                print(canonical(prepare(args.acolite)))
                return 0
            catalog = Catalog(args.storage)
            catalog_notice(catalog)
            try:
                code = offline_command(catalog, args)
                return profile_command(catalog, args) if code is None else code
            finally:
                catalog.db.close()
    except KeyboardInterrupt:
        print('Interrumpido; lo parcial se limpiará con recover (automático al iniciar run y search).')
        return 130
    except ValueError as error:
        # Validaciones locales (perfil, nombres, rutas): el mensaje no trae datos remotos.
        print('Error:', error)
        return 2
    except Exception as error:
        # No imprimir respuestas remotas ni excepciones con credenciales.
        print('OCEANOS no completó la operación:', type(error).__name__)
        print('Revise los eventos del catálogo (oceanos status N).')
        return 1
