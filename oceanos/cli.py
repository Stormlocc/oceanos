"""Interfaz manual del MVP; ejecutar dentro del entorno ACOLITE de WSL."""
import argparse
import json
import sys
from pathlib import Path
from .catalog import Catalog
from .config import ROOT, ACOLITE, PRODUCTS, canonical, disk_bytes, exclusive, file_hash, instant, profile
from .native import prepare, scene_identity, eligible
from .pipeline import Pipeline, cleanup, recover, roots
from .progress import Progress, size, duration
from .resources import plan
from .sync import sync


SENSORS = {'sentinel2': 'project.yaml', 'landsat': 'landsat.yaml'}
SATELLITES = {'S2A': 'sentinel2', 'S2B': 'sentinel2', 'S2C': 'sentinel2', 'L8': 'landsat', 'L9': 'landsat'}
STATES = ['EN_CURSO', 'OK', 'OMITIDO', 'FALLIDO', 'INTERRUMPIDO', 'IMPORTADO']
DATE = 'AAAA-MM-DD[THH:MM:SSZ]'


def date_text(value):
    """Valida una fecha UTC ISO 8601 y la devuelve sin cambios."""
    try:
        instant(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"fecha inválida '{value}': use {DATE}, p. ej. 2026-08-01 o 2026-08-01T00:00:00Z") from None
    return value


def product_list(value):
    """Valida productos separados por coma contra los soportados."""
    items = [item.strip() for item in value.split(',')]
    unknown = [item for item in items if item not in PRODUCTS]
    if unknown or not all(items):
        raise argparse.ArgumentTypeError(f"producto no soportado {', '.join(unknown) or '(vacío)'}; "
                                         f"opciones: {', '.join(sorted(PRODUCTS))} (OC4 excluido)")
    return items


def satellite_list(value):
    """Valida satélites separados por coma (S2A,S2B,S2C,L8,L9); acepta minúsculas y LC08/LC09."""
    items = [item.strip().upper().replace('LC0', 'L') for item in value.split(',')]
    unknown = [item for item in items if item not in SATELLITES]
    if unknown:
        raise argparse.ArgumentTypeError(f"satélite desconocido {', '.join(unknown)}; opciones: "
                                         "S2A, S2B, S2C (sentinel2) o L8, L9 (landsat)")
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
    """Agrega --sensor, --satelite, --start y --end; en subcomandos no pisan lo dado antes del comando."""
    hidden = {} if top else {'default': argparse.SUPPRESS}
    group = parser.add_argument_group('selección de escenas' + ('' if top else ' (también válidas antes del comando)'))
    group.add_argument('--sensor', choices=list(SENSORS), **hidden,
                       help='familia de sensor: sentinel2 (perfil project.yaml) o landsat (perfil landsat.yaml). '
                            'Por defecto la del --profile')
    group.add_argument('--satelite', type=satellite_list, metavar='SAT[,SAT]', **hidden,
                       help='solo esos satélites: S2A, S2B, S2C (sentinel2) o L8, L9 (landsat), separados por coma. '
                            'Por defecto todos los del perfil')
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
        'Pipeline OCEANOS: catálogo SQLite local y ACOLITE nativo.\n\n'
        'Orden habitual:\n'
        '  oceanos prepare                       # una vez: verificar ACOLITE\n'
        '  oceanos sync                          # registrar L1R/L2W copiados a storage/importados\n'
        '  oceanos search                        # ver escenas remotas (no descarga)\n'
        '  oceanos search --registrar            # dejarlas en la cola\n'
        '  oceanos cola                          # revisar la cola\n'
        '  oceanos run                           # descargar y procesar la cola\n'
        '  oceanos status --ultimas 5            # revisar resultados\n\n'
        'Ayuda de cada comando: oceanos <comando> -h'), **options))
    general = result.add_argument_group('rutas y perfil')
    general.add_argument('--storage', type=Path, default=ROOT/'storage', metavar='CARPETA',
                         help='catálogo, runs e importados. Por defecto: storage/')
    general.add_argument('--acolite', type=Path, default=ACOLITE, metavar='CARPETA',
                         help=f'instalación de ACOLITE. Por defecto: {ACOLITE}')
    general.add_argument('--profile', type=Path, metavar='YAML',
                         help='perfil AOI/sensor. Por defecto: config/aoi/lapargera_v1/project.yaml '
                              '(o landsat.yaml con --sensor landsat)')
    general.add_argument('--products', type=product_list, metavar='PROD[,PROD]',
                         help='productos L2W separados por coma, entre: ' + ', '.join(sorted(PRODUCTS))
                              + '. NDCI solo Sentinel-2; OC4 excluido. Por defecto los del perfil')
    selection(result, top=True)
    commands = result.add_subparsers(dest='command', required=True, metavar='COMANDO', title='comandos')

    def command(name, summary, description='', examples=''):
        """Crea un subcomando con ayuda en español y ejemplos al final."""
        sub = commands.add_parser(name, help=summary, description=summary + ('\n\n'+description if description else ''),
                                  epilog=('ejemplos:\n'+examples) if examples else None, **options)
        return spanish(sub)

    command('prepare', 'Verificar la revisión de ACOLITE y aplicar el parche de catálogo',
            examples='  oceanos prepare')
    search = command('search', 'Consultar el catálogo remoto (CDSE o USGS) sin descargar escenas',
        'Muestra fecha UTC, satélite, tile, tamaño L1 (L1C SAFE en Sentinel-2, Product Bundle\n'
        'en Landsat), nubosidad, estado local y nombre de la escena:\n'
        '  NUEVA          aún no descargada ni en cola\n'
        '  PENDIENTE      en la cola; la procesará run\n'
        '  FALLIDA        falló el último intento; run la reintenta\n'
        '  PROCESADA      ya tiene L1R/L2W propios\n'
        '  DISPONIBLE     la misma adquisición ya tiene L2W (propio o importado)\n'
        '  IMPORTADA      registrada con sync\n'
        'Debajo explica la consulta:\n'
        '  completitud    COMPLETE (están todas), INCOMPLETE (el proveedor tiene más) o\n'
        '                 UNKNOWN (el proveedor no informó el total)\n'
        '  descartadas    escenas que el proveedor devuelve por tocar el rectángulo del AOI pero\n'
        '                 que no cumplen el perfil (tile o path/row, satélite, intervalo), con su motivo\n'
        'Sin --registrar no se compromete ninguna descarga.',
        '  oceanos search\n'
        '  oceanos search --sensor landsat\n'
        '  oceanos search --satelite S2B,S2C --start 2026-03-01 --end 2026-04-01\n'
        '  oceanos search --registrar                  # todas las NUEVAS\n'
        '  oceanos search --registrar 20260116 20260205   # solo esas (fragmento del nombre)')
    selection(search)
    search.add_argument('--registrar', nargs='*', metavar='ESCENA',
                        help='dejar en la cola para run: sin nombres, todas las NUEVAS; con nombres o fragmentos '
                             'únicos (p. ej. 20260215), solo esas')
    search.add_argument('--json', action='store_true', help='imprimir solo los nombres de las escenas en JSON')
    run = command('run', 'Descargar y procesar con ACOLITE las escenas de la cola (no repite search)',
        'Sin opciones procesa las escenas PENDIENTE o FALLIDA de la cola que caen en el\n'
        'sensor/satélite/intervalo elegidos; las demás quedan pendientes. Muestra barra de\n'
        'progreso y, al final, tiempos y disco ocupado por L1R/L2W.\n\n'
        'Paralelo: varias escenas avanzan a la vez hasta su L2W usando como máximo el 70 % de\n'
        'la CPU y de la RAM del equipo. Cada etapa (descarga, extracción, ACOLITE) arranca solo\n'
        'si su pico de RAM medido cabe en ese 70 %; el resto espera. El número de escenas a la\n'
        'vez se calcula al iniciar según CPU, RAM, historial del catálogo y disco libre.',
        '  oceanos run\n'
        '  oceanos run --trabajadores 1               # una escena a la vez (como antes)\n'
        '  oceanos run --satelite S2B\n'
        '  oceanos run --sensor landsat\n'
        '  oceanos run --escena 20260215\n'
        '  oceanos run --source /ruta/escena.zip --scene S2B_MSIL1C_20260804T150719_N0512_R082_T19QGV_20260804T182348.SAFE')
    selection(run)
    local = run.add_argument_group('una sola escena')
    local.add_argument('--escena', '--version', dest='version', metavar='ESCENA',
                       help='procesar solo esta escena (nombre o fragmento único, p. ej. 20260215), esté o no en la cola')
    local.add_argument('--source', type=Path, metavar='ARCHIVO', help='ZIP (Sentinel-2) o TAR (Landsat) local; requiere --scene')
    local.add_argument('--scene', metavar='NOMBRE',
                       help='nombre nativo de la escena, p. ej. S2B_MSIL1C_20260804T150719_N0512_R082_T19QGV_20260804T182348.SAFE '
                            'o LC09_L1TP_005048_20260805_20260806_02_T1')
    run.add_argument('--force', action='store_true', help='reprocesar aunque ya exista un L2W verificado')
    run.add_argument('--trabajadores', type=workers_count, metavar='N',
                     help='escenas a la vez (1 = secuencial). Por defecto se calcula con el 70 %% de CPU y RAM; '
                          'la RAM de cada etapa se respeta igual')
    derive = command('derive', 'Regenerar L2W desde un L1R sin descargar (repite la corrección atmosférica)',
        examples="  oceanos --products 'Rrs_*,chl_oc3,fai,ndvi' derive --l1r storage/runs/0007_S2B_2026-02-15/X_L1R.nc --scene NOMBRE.SAFE")
    selection(derive)
    derive.add_argument('--l1r', type=Path, required=True, metavar='ARCHIVO', help='L1R NetCDF de entrada (obligatorio)')
    derive.add_argument('--scene', required=True, metavar='NOMBRE', help='nombre nativo de la escena (obligatorio)')
    status = command('status', 'Mostrar procesos desde SQLite (sin ACOLITE ni red)',
        examples='  oceanos status\n  oceanos status --ultimas 5\n  oceanos status --estado FALLIDO\n  oceanos status 7')
    status.add_argument('run', nargs='?', metavar='PROCESO', help='número de proceso: detalle con archivos, métricas y eventos')
    status.add_argument('--ultimas', type=int, metavar='N', help='solo los N procesos más recientes')
    status.add_argument('--estado', choices=STATES, metavar='ESTADO', help='filtrar por estado: '+', '.join(STATES))
    queue = command('cola', 'Ver la cola de descargas registrada por search --registrar (sin red)',
        'Estados: PENDIENTE, FALLIDA (se reintenta en el próximo run), PROCESADA, DISPONIBLE, IMPORTADA.',
        '  oceanos cola\n  oceanos cola --quitar 20260116 20260205')
    queue.add_argument('--quitar', nargs='+', metavar='ESCENA', help='retirar de la cola escenas no procesadas (nombre o fragmento único)')
    imports = command('sync', 'Registrar L1R/L2W copiados a mano a una carpeta de storage, solo por el nombre',
        'Nombres reconocidos (salida ACOLITE):\n'
        '  S2B_MSI_2026_02_15_15_07_58_T19QGV_lapargera_v1_L2W.nc\n'
        '  L9_OLI_2026_08_05_14_57_33_005048_lapargera_v1_L1R.nc\n'
        'En storage/runs cada subcarpeta se adopta como un proceso y se renombra (0001_S2B_2026-01-06).',
        '  oceanos sync\n  oceanos sync storage/importados/pc2 --hash\n  oceanos sync storage/runs --hash')
    imports.add_argument('carpeta', nargs='?', type=Path, metavar='CARPETA',
                         help='carpeta dentro de storage, salvo catalog y temporary. Por defecto: storage/importados')
    imports.add_argument('--hash', action='store_true', help='calcular también el SHA-256 de cada archivo (lento)')
    command('recover', 'Registrar interrupciones y limpiar lo parcial (automático al iniciar search/run/derive)',
            examples='  oceanos recover')
    clean = command('cleanup', 'Evaluar la limpieza de temporales de un proceso',
                    examples='  oceanos cleanup 7')
    clean.add_argument('run', type=int, metavar='PROCESO', help='número de proceso (ver status)')
    return result


def load_profile(args):
    """Carga el perfil según --profile/--sensor/--satelite y valida que sean coherentes."""
    path = args.profile
    if args.sensor and not path:
        path = ROOT/'config/aoi/lapargera_v1'/SENSORS[args.sensor]
    config = profile(path or ROOT/'config/aoi/lapargera_v1/project.yaml', args.products, args.start, args.end, args.satelite)
    if args.sensor and config['family'] != args.sensor:
        raise ValueError(f"El perfil {path} es {config['family']}, no {args.sensor}")
    return config


def table(rows, columns):
    """Imprime filas (dicts) como tabla de texto alineada con las columnas indicadas."""
    text = lambda value: '—' if value is None else str(value)
    widths = [max(len(title), *(len(text(row[key])) for row in rows)) for title, key in columns]
    print('  '.join(title.ljust(width) for (title, _), width in zip(columns, widths)))
    for row in rows:
        print('  '.join(text(row[key]).ljust(width) for (_, key), width in zip(columns, widths)))


def show_versions(catalog, scenes, config):
    """Tabla de search con fecha, tamaño, nubosidad y estado de cada escena; devuelve las filas."""
    done = catalog.completed(config['aoi']['id'])
    rows = []
    for scene in scenes:
        row = dict(catalog.db.execute('SELECT * FROM escenas WHERE escena=?', (scene,)).fetchone())
        if row['adquisicion'] in done and row['estado'] in ('NUEVA', 'PENDIENTE', 'FALLIDA'):
            catalog.scene_state(scene, 'DISPONIBLE')
            row['estado'] = 'DISPONIBLE'
        row['tamano'] = f"{row['tamano_mb']:,.1f} MB" if row['tamano_mb'] else 'no informado'
        rows.append(row)
    rows.sort(key=lambda row: row['fecha_utc'])
    if rows:
        table(rows, [('FECHA (UTC)', 'fecha_utc'), ('SAT', 'satelite'), ('TILE', 'tile'), ('TAMAÑO L1', 'tamano'),
                     ('NUBES %', 'nubosidad'), ('ESTADO', 'estado'), ('ESCENA', 'escena')])
    total = lambda items: size(sum((r['tamano_mb'] or 0)*1e6 for r in items))
    new = [row for row in rows if row['estado'] == 'NUEVA']
    unknown = sum(row['tamano_mb'] is None for row in rows)
    print(f"\n{len(rows)} escenas · {total(rows)} en L1" + (f" (sin contar {unknown} sin tamaño)" if unknown else '')
          + f" · {len(new)} nuevas ({total(new)}) · "
          + ' · '.join(f"{sum(r['estado'] == state for r in rows)} {label}"
                       for state, label in (('PENDIENTE', 'en cola'), ('FALLIDA', 'fallidas'), ('PROCESADA', 'procesadas'),
                                            ('DISPONIBLE', 'ya disponibles'), ('IMPORTADA', 'importadas'))
                       if any(r['estado'] == state for r in rows)))
    return rows


COMPLETENESS = {
    'COMPLETE': 'completa: el proveedor devolvió todas las escenas que coinciden con la búsqueda',
    'INCOMPLETE': 'INCOMPLETA: el proveedor tiene más coincidencias que las devueltas (ACOLITE pide hasta '
                  '1000 sin paginar); acote --start/--end y repita',
    'UNKNOWN': 'desconocida: el proveedor no informó el total de coincidencias (totalHits), '
               'no se puede asegurar que estén todas'}


def show_query(report):
    """Explica la consulta al proveedor: devueltas, completitud, descartadas por el perfil y tamaños."""
    if not report:
        return
    counts = report.get('provider_counts') or {}
    total = f" de {counts['totalHits']} coincidencias" if counts.get('totalHits') is not None else ''
    print(f"\nConsulta {report['provider']}: {report.get('returned', report['count'])} escenas devueltas{total}, "
          f"{report['count']} cumplen el perfil.")
    print('Completitud '+COMPLETENESS.get(report['completeness'], report['completeness'])+'.')
    excluded = report.get('excluded_by_profile') or []
    if excluded:
        print(f'Descartadas por el perfil ({len(excluded)}): el proveedor las devuelve porque tocan el rectángulo '
              'del AOI, pero no cumplen el perfil; no aparecen en la tabla ni se pueden registrar.')
        for item in excluded:
            print(f"  {item['product']} — {item['reason']}")
    sizes = report.get('sizes', 'OK')
    status, _, missing = sizes.partition(';FALTAN:')
    if status.startswith('NO_DISPONIBLE'):
        print(f"Tamaños: USGS no los entregó ({status.split(':', 1)[1]}). download-options de M2M requiere el rol "
              'MACHINE y la página de opciones de EarthExplorer no los mostró. La descarga no depende de esto.')
    elif status == 'M2M':
        print('Tamaños: Product Bundle L1 según download-options de USGS M2M.')
    elif status == 'EARTHEXPLORER':
        print('Tamaños: Product Bundle L1 según la página de descarga de EarthExplorer (redondeado a 0.01 MiB); '
              'download-options de M2M no está permitido para esta cuenta (requiere el rol MACHINE).')
    if missing:
        print(f'  {missing} escenas quedaron sin tamaño informado.')


def register(catalog, rows, selected):
    """Pone en la cola las escenas elegidas de search; omite las que ya tienen L1R/L2W."""
    if selected:
        wanted = {catalog.resolve_scene(text) for text in selected}
        unknown = wanted - {row['escena'] for row in rows}
        if unknown:
            raise ValueError('Escenas fuera de esta búsqueda: '+', '.join(sorted(unknown)))
        chosen = [row for row in rows if row['escena'] in wanted]
    else:
        chosen = [row for row in rows if row['estado'] in ('NUEVA', 'FALLIDA')]
    done = ('DISPONIBLE', 'PROCESADA', 'IMPORTADA')
    skipped = [row for row in chosen if row['estado'] in done]
    chosen = [row for row in chosen if row['estado'] not in done]
    catalog.enqueue([row['escena'] for row in chosen])
    if skipped:
        print(f'Omitidas {len(skipped)} que ya tienen L2W: '+', '.join(r['escena'] for r in skipped))
    print(f"Registradas {len(chosen)} escenas para descarga ({size(sum((r['tamano_mb'] or 0)*1e6 for r in chosen))} en L1). "
          "Ejecute 'oceanos run' para procesarlas.")


def show_queue(catalog):
    """Tabla de la cola de descargas."""
    items = catalog.queue()
    if not items:
        print("Cola vacía. Use 'oceanos search --registrar' para registrar escenas.")
        return
    table(items, [('FECHA (UTC)', 'fecha_utc'), ('SAT', 'satelite'), ('TAMAÑO MB', 'tamano_mb'), ('ESTADO', 'estado'),
                  ('PROCESOS', 'procesos'), ('ÚLTIMO', 'ultimo'), ('REGISTRADA', 'registrada'), ('ESCENA', 'escena')])
    counts = {}
    for item in items:
        counts[item['estado']] = counts.get(item['estado'], 0) + 1
    print('\n'+' · '.join(f'{state}: {count}' for state, count in sorted(counts.items())))


def show_runs(rows):
    """Tabla de procesos para status."""
    if not rows:
        print('Sin procesos registrados.')
        return
    table(rows, [('ID', 'id'), ('FECHA ESCENA', 'fecha_utc'), ('SAT', 'satelite'), ('TIPO', 'tipo'), ('ESTADO', 'estado'),
                 ('INICIO', 'inicio'), ('MIN', 'duracion_min'), ('DESCARGA MIN', 'descarga_min'), ('INTENTOS', 'intentos'),
                 ('ARCHIVOS', 'archivos'), ('ERROR', 'error')])


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


def show_summary(catalog, result):
    """Resumen al terminar run: estados, tiempos, descarga y disco ocupado por L1R/L2W."""
    runs = result['runs']
    rows = [catalog.process(run) for run in runs]
    states = {}
    for row in rows:
        states[row['estado']] = states.get(row['estado'], 0) + 1
    downloaded = [row for row in rows if row['descarga_min']]
    seconds = sum(row['descarga_min']*60 for row in downloaded)
    volume = sum((row['descarga_mb'] or 0)*1e6 for row in downloaded)
    retried = [row for row in rows if (row['intentos'] or 0) > 1]
    print('\n══ Resumen del run ══')
    print(f"Escenas: {len(rows)} · " + ' · '.join(f'{state} {count}' for state, count in sorted(states.items()))
          + f' · con reintentos {len(retried)}')
    print(f"Tiempo total: {duration(result['seconds'])} · descarga {duration(seconds)} "
          f"({size(volume)}" + (f", {size(volume/seconds)}/s promedio)" if seconds else ')'))
    for label, usage in (('Generado en este run', catalog.disk(set(runs))), ('Total en storage', catalog.disk())):
        print(f'{label}: ' + ' · '.join(f"{kind} {size(item['bytes'])} ({item['archivos']} archivos)"
                                         for kind, item in usage.items()))
    if rows:
        print('Detalle:')
        for row in rows:
            minutes = lambda value: duration(value*60) if value is not None else '—'
            print(f"  {row['id']:>4}  {row['estado']:<12} descarga {minutes(row['descarga_min']):>7} "
                  f"{size((row['descarga_mb'] or 0)*1e6) if row['descarga_mb'] else '—':>9}  intentos {row['intentos'] or 0}"
                  f"  total {minutes(row['duracion_min']):>7}  {row['carpeta']}")


def main(argv=None):
    """Ejecuta un subcomando bajo el bloqueo exclusivo del catálogo y devuelve el código de salida."""
    args = parser().parse_args(argv)
    try:
        with exclusive(args.storage):
            if args.command=='prepare':
                print(canonical(prepare(args.acolite)))
                return 0
            catalog = Catalog(args.storage)
            if catalog.backup:
                print(f'Catálogo anterior guardado como {catalog.backup.relative_to(catalog.storage)}; '
                      "se empezó uno nuevo. Use 'oceanos sync storage/runs' para registrar los L1R/L2W existentes.")
            try:
                if args.command=='status':
                    if args.run:
                        show_detail(catalog.run_detail(args.run))
                    else:
                        show_runs(catalog.runs(args.estado,args.ultimas))
                    return 0
                if args.command=='recover':
                    result = recover(catalog)
                    print(json.dumps(result,ensure_ascii=False))
                    return 1 if result['limpieza_fallida'] else 0
                if args.command=='cleanup':
                    print(cleanup(catalog,args.run))
                    return 0
                if args.command=='cola':
                    for text in args.quitar or []:
                        catalog.dequeue(catalog.resolve_scene(text))
                    show_queue(catalog)
                    return 0
                if args.command=='sync':
                    report = sync(catalog,args.carpeta or args.storage/'importados',hashed=args.hash)
                    for item in report['importados']:
                        print(f"  proceso {item['proceso']:>4}  {item['tipo']}  {item['archivo']}")
                    for key in ('reaparecidos','desaparecidos','no_reconocidos','duplicados'):
                        for name in report[key]:
                            print(f'  {key}: {name}')
                    print(f"Importados {len(report['importados'])} archivos · ya registrados {report['ya_registrados']} · "
                          f"no reconocidos {len(report['no_reconocidos'])} · desaparecidos {len(report['desaparecidos'])}")
                    return 0
                # Carga el AOI/perfil
                config = load_profile(args)
                pipeline = Pipeline(catalog, config, args.acolite,
                                    progress=Progress() if args.command in ('run','derive') else None)
                recovered = recover(catalog)
                if recovered['limpiados'] or recovered['limpieza_fallida']:
                    print('Recuperación:',json.dumps(recovered,ensure_ascii=False))
                # DERIVE o RUN con fuente local requieren archivo existente.
                if args.command=='derive' or getattr(args,'source',None):
                    path = args.l1r if args.command=='derive' else args.source
                    if not getattr(args,'scene',None) or not path.is_file():
                        raise ValueError('Se requiere archivo existente y --scene')
                    source = {'provider':'LOCAL','product':args.scene,
                              'format':'L1R' if args.command=='derive' else ('SAFE' if config['family']=='sentinel2' else 'TAR'),
                              'local':str(path.resolve()),'sha256':file_hash(path),
                              'identity':scene_identity(args.scene),'metadata':{'identity_origin':'nombre_del_producto'}}
                    if not eligible(source,config):
                        raise ValueError('Escena fuera del sensor, intervalo o tile/path/row del perfil')
                    # Una escena ya conocida del proveedor conserva su fuente; el archivo local solo se usa aquí.
                    if not catalog.db.execute('SELECT 1 FROM escenas WHERE escena=?',(args.scene,)).fetchone():
                        catalog.upsert_scene(source, seen=False)
                    pipeline.run(args.scene,source=source,local_l1r=path if args.command=='derive' else None,
                                 force=getattr(args,'force',False))
                # SEARCH o RUN sin fuente local.
                elif args.command=='search':
                    scenes = pipeline.search()
                    if args.json:
                        print(canonical({'escenas':scenes}))
                        return 0
                    rows = show_versions(catalog,scenes,config)
                    show_query(pipeline.last_query)
                    if args.registrar is None:
                        print("Solo consulta: nada quedó registrado para descarga. "
                              "Use 'oceanos search --registrar [ESCENA ...]' para que 'oceanos run' las procese.")
                    else:
                        register(catalog,rows,args.registrar)
                    return 0
                else:
                    # RUN: trabaja sobre la cola registrada por search; no vuelve a consultar al proveedor.
                    if args.version:
                        scenes = [catalog.resolve_scene(args.version)]
                    else:
                        scenes, outside, available = catalog.pending(config,force=args.force)
                        if available:
                            print(f'{len(available)} en cola ya tienen L2W; marcadas DISPONIBLE.')
                        if outside:
                            print(f'{len(outside)} en cola quedan fuera del perfil/intervalo actual y se conservan pendientes.')
                        if not scenes:
                            print("No hay escenas pendientes. Use 'oceanos search --registrar' para registrarlas.")
                            return 0
                        print(f'Escenas por procesar: {len(scenes)}')
                    if len(scenes) > 1 and args.trabajadores != 1:
                        free = config['budget']-disk_bytes(roots(catalog.storage,args.acolite))
                        pipeline.resources = plan(catalog,config,free,args.trabajadores)
                        print(pipeline.resources.describe())
                    result = pipeline.batch(scenes,force=args.force)
                    show_summary(catalog,result)
                    return 1 if result['failed'] else 0
                return 0
            finally:
                catalog.db.close()
    except KeyboardInterrupt:
        print('Interrumpido; lo parcial se limpiará con recover (automático al iniciar search/run/derive).')
        return 130
    except ValueError as error:
        # Validaciones locales (perfil, nombres, rutas): el mensaje no trae datos remotos.
        print('Error:', error)
        return 2
    except Exception as error:
        # No imprimir respuestas remotas ni excepciones con credenciales.
        print('OCEANOS no completó la operación:',type(error).__name__)
        print('Revise los eventos del catálogo (oceanos status N).')
        return 1
