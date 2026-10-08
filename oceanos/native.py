"""Adaptación estrecha a las funciones nativas de la revisión auditada."""
import contextlib
import hashlib
import re
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .config import ROOT, REVISION, file_hash, instant


def prepare(path):
    """Verifica la revisión de ACOLITE, aplica el parche si falta y devuelve la identidad del motor."""
    path = Path(path).resolve()
    revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('ACOLITE no corresponde a la revisión auditada')
    patch = ROOT/'patches/acolite-catalog.patch'
    check = subprocess.run(['git', '-C', str(path), 'apply', '--reverse', '--check', str(patch)], capture_output=True)
    if check.returncode:
        if subprocess.check_output(['git', '-C', str(path), 'diff', '--name-only']).strip():
            raise ValueError('ACOLITE tiene cambios previos: conservarlos y usar una copia limpia')
        subprocess.run(['git', '-C', str(path), 'apply', '--check', str(patch)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(path), 'apply', str(patch)], check=True)
    return identity(path)


def identity(path):
    """Devuelve la identidad del motor: revisión, SHA-256 del parche y SHA-256 del diff local."""
    revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('Revisión ACOLITE inesperada')
    patch = ROOT/'patches/acolite-catalog.patch'
    subprocess.run(['git', '-C', str(path), 'apply', '--reverse', '--check', str(patch)], check=True, capture_output=True)
    # Registrar todos los cambios locales; no atribuirlos al commit upstream.
    diff = subprocess.check_output(['git', '-C', str(path), 'diff', '--binary'])
    return {'revision': revision, 'patch_sha256': file_hash(patch), 'working_diff_sha256': hashlib.sha256(diff).hexdigest()}


def load(path):
    """Importa ACOLITE desde la ruta indicada."""
    sys.path.insert(0, str(Path(path).resolve()))
    import acolite
    return acolite


def scene_identity(name):
    """Extrae familia, plataforma, fecha, tile o path/row y baseline del nombre de la escena."""
    if re.fullmatch(r'S2[ABC]_MSIL1C_\d{8}T\d{6}_N\d{4}_R\d{3}_T\w{5}_\d{8}T\d{6}(\.SAFE)?', name):
        fields = name.split('_')
        return {'family': 'sentinel2', 'platform': fields[0], 'date': fields[2],
                'tile': fields[5][1:], 'baseline': fields[3],
                'acquisition_key': ':'.join([fields[0], fields[2], fields[4], fields[5]])}
    if re.fullmatch(r'LC0[89]_L1TP_\d{6}_\d{8}_\d{8}_02_T1', name):
        fields = name.split('_')
        return {'family': 'landsat', 'platform': fields[0], 'date': fields[3],
                'path': int(fields[2][:3]), 'row': int(fields[2][3:]),
                'baseline': ':'.join(fields[4:]), 'acquisition_key': ':'.join(fields[:1]+fields[2:4])}
    raise ValueError('Identificador de escena no soportado')


# Nombre de salida ACOLITE: <sensor>_<AAAA_MM_DD_HH_MM_SS>_<tile o path/row>[_<región>]_<L1R|L2W>.nc
OUTPUT_NAME = re.compile(r'(?P<sensor>S2[ABC]_MSI|L[89]_OLI)_(?P<time>\d{4}(?:_\d{2}){5})_'
                         r'(?P<place>T\d{2}[A-Z]{3}|\d{6})(?:_(?P<region>.+?))?_(?P<level>L1R|L2W)\.nc')


def output_identity(name):
    """Identidad de un L1R/L2W de ACOLITE solo por su nombre de archivo, sin abrirlo.

    El instante del nombre es el de sensado del gránulo, no el del producto L1C; por eso la
    relación con una escena del catálogo se hace por `acquisition_day`.
    """
    match = OUTPUT_NAME.fullmatch(name)
    if not match:
        raise ValueError('Nombre de salida ACOLITE no reconocido')
    sensor, place = match['sensor'].split('_')[0], match['place']
    date = datetime.strptime(match['time'], '%Y_%m_%d_%H_%M_%S').strftime('%Y%m%dT%H%M%S')
    if sensor.startswith('S2'):
        info = {'family': 'sentinel2', 'platform': sensor, 'tile': place[1:]}
    else:
        info = {'family': 'landsat', 'platform': 'LC0'+sensor[1], 'path': int(place[:3]), 'row': int(place[3:])}
    info.update(date=date, baseline='DESCONOCIDA')
    info['acquisition_key'] = acquisition_day(info)
    return {**info, 'region': match['region'], 'level': match['level']}


def acquisition_day(info):
    """Clave plataforma:día:tile (o path/row), común a un producto L1C y a sus salidas ACOLITE."""
    place = info.get('tile') or '{:03d}{:03d}'.format(info['path'], info['row'])
    return ':'.join([info['platform'], info['date'][:8], place])


def scene_date(source):
    """Fecha y hora UTC legible: ContentDate (CDSE), Start Time (USGS) o la del nombre."""
    metadata = source.get('metadata', {})
    start = metadata.get('ContentDate', {}).get('Start') or metadata.get('Start Time')
    if start:
        return instant(start.replace(' ', 'T')).strftime('%Y-%m-%d %H:%M')
    raw = source['identity']['date']
    return datetime.strptime(raw, '%Y%m%dT%H%M%S' if 'T' in raw else '%Y%m%d').strftime('%Y-%m-%d %H:%M')


def exclusion(source, config):
    """Motivo legible por el que una fuente no cumple el perfil (sensor, intervalo, tile o path/row, satélite); None si lo cumple."""
    info = source['identity']
    if info['family'] != config['family']:
        return f"familia {info['family']} (perfil {config['family']})"
    raw = info['date']
    date = datetime.strptime(raw, '%Y%m%dT%H%M%S' if 'T' in raw else '%Y%m%d').replace(tzinfo=timezone.utc)
    if source.get('metadata', {}).get('ContentDate', {}).get('Start'):
        date = instant(source['metadata']['ContentDate']['Start'])
    # Landsat usa fecha derivada del nombre cuando la API no expone hora normalizada.
    if not instant(config['start']) <= date < instant(config['end']):
        return f"fecha {date:%Y-%m-%d} fuera del intervalo {config['start'][:10]} a {config['end'][:10]} (fin excluido)"
    search = config['search']
    if info['family'] == 'sentinel2':
        if info['tile'] != search['tile']:
            return f"tile {info['tile']} (perfil {search['tile']})"
        platform = info['platform']
    else:
        if (info['path'], info['row']) != (search['wrs_path'], search['wrs_row']):
            return (f"path/row {info['path']:03d}/{info['row']:03d} (perfil {search['wrs_path']:03d}/{search['wrs_row']:03d}): "
                    "toca el rectángulo del AOI pero no es la escena configurada")
        # Perfil Landsat usa L8/L9; la identidad de USGS, LC08/LC09.
        platform = 'L'+info['platform'][-1]
    if platform not in search.get('platforms', [platform]):
        return f"satélite {platform} no seleccionado (perfil {', '.join(search['platforms'])})"
    return None


def eligible(source, config):
    """Indica si una fuente cumple el sensor, el intervalo y el tile o path/row del perfil."""
    return exclusion(source, config) is None


def l1_bytes(source):
    """Tamaño del producto L1 a descargar: ContentLength (CDSE) o filesize del Product Bundle (USGS)."""
    metadata = source.get('metadata', {})
    return metadata.get('ContentLength') or metadata.get('filesize')


@contextlib.contextmanager
def observe_post(endpoint):
    """Guarda los contadores de las respuestas de `endpoint` que ACOLITE pide con requests.Session.post.

    La función nativa descarta totalHits/recordsReturned; observarlos aquí evita modificar ACOLITE.
    """
    import requests
    seen, original = [], requests.Session.post

    def post(session, url, *args, **kwargs):
        response = original(session, url, *args, **kwargs)
        if str(url).endswith('/'+endpoint):
            try:
                data = response.json().get('data') or {}
                seen.append({k: data.get(k) for k in ('totalHits', 'totalHitsAccuracy', 'recordsReturned',
                                                      'numExcluded', 'nextRecord')})
            except (ValueError, AttributeError):
                pass
        return response
    requests.Session.post = post
    try:
        yield seen
    finally:
        requests.Session.post = original


def usgs_completeness(stats):
    """COMPLETE si USGS devolvió todos los resultados, INCOMPLETE si hay más, UNKNOWN sin contadores."""
    if not stats or stats.get('totalHits') is None or stats.get('recordsReturned') is None:
        return 'UNKNOWN'
    if stats['recordsReturned'] < stats['totalHits']:
        return 'INCOMPLETE'
    # Con sceneFilter USGS calcula totalHits sobre la consulta; 'approximate' es un conteo en caché.
    return 'UNKNOWN' if stats.get('totalHitsAccuracy') == 'approximate' else 'COMPLETE'


def usgs_sizes(ac, dataset, entities):
    """Tamaño (bytes) del Product Bundle de cada escena según download-options de M2M.

    Devuelve ({entityId: bytes}, None) o ({}, código) si USGS no los entrega; download-options
    requiere el rol MACHINE de la cuenta M2M.
    """
    import json
    import requests
    if not entities:
        return {}, None
    token = ac.api.earthexplorer.auth(netrc_machine='earthexplorer_token')
    if not token:
        return {}, 'SIN_TOKEN'
    response = requests.post(ac.config['EARTHEXPLORER_api']+'/download-options', headers={'X-Auth-Token': token},
                             data=json.dumps({'datasetName': dataset, 'entityIds': entities}), timeout=120)
    try:
        payload = response.json()
    except ValueError:
        return {}, f'HTTP_{response.status_code}'
    if payload.get('errorCode') or not isinstance(payload.get('data'), list):
        # errorCode es un código de USGS (p. ej. permisos); el mensaje no se guarda.
        return {}, str(payload.get('errorCode') or 'SIN_DATOS')
    sizes = {}
    for option in payload['data']:
        name, entity = option.get('productName') or '', option.get('entityId')
        if entity in entities and 'Product Bundle' in name and option.get('filesize'):
            # Preferir el bundle Level-1 si hubiera varios.
            if entity not in sizes or 'Level-1' in name:
                sizes[entity] = int(option['filesize'])
    return sizes, None


UNITS = {'KiB': 1024, 'MiB': 1024**2, 'GiB': 1024**3}


def bundle_size(html, entity):
    """Bytes del botón 'Download Product' (Product Bundle) de una escena en la página de opciones de EarthExplorer.

    EarthExplorer lo muestra redondeado a centésimas de MiB; los botones de bandas usan otro
    data-entityId y el título 'Download Product/File'.
    """
    for button in re.findall(r'<button\b[^>]*>.*?</button>', html, flags=re.S):
        head = button[:button.index('>')]
        if (f'data-entityId="{entity}"' in head and 'title="Download Product"' in head
                and 'secondaryDownloadButton' in head):
            match = re.search(r'([\d,]+(?:\.\d+)?)\s*(KiB|MiB|GiB)', button)
            if match:
                return int(float(match[1].replace(',', ''))*UNITS[match[2]])
    return None


def earthexplorer_sizes(ac, dataset, entities):
    """Respaldo de usgs_sizes: lee el tamaño de la misma página de opciones que usa la descarga nativa.

    Inicia sesión en EROS como ac.api.earthexplorer.download; devuelve ({entityId: bytes}, None)
    o ({}, código). No descarga escenas.
    """
    import requests
    if not entities:
        return {}, None
    auth = ac.shared.auth('earthexplorer')
    if auth is None:
        return {}, 'SIN_CREDENCIALES_EARTHEXPLORER'
    session = requests.Session()
    session.headers['X-Auth-Token'] = f"{ac.api.earthexplorer.auth(netrc_machine='earthexplorer_token')}"
    page = session.get(ac.config['EARTHEXPLORER_ers']+'/login', timeout=60)
    csrf = re.findall(r'name="csrf" value="(.+?)"', page.text)
    if not csrf:
        return {}, 'LOGIN_EARTHEXPLORER'
    session.post(ac.config['EARTHEXPLORER_ers']+'/login', data={'username': auth[0], 'password': auth[1], 'csrf': csrf[0]},
                 allow_redirects=True, timeout=60)
    sizes = {}
    for entity in entities:
        html = session.get('{}/options/{}/{}'.format(ac.config['EARTHEXPLORER_download'], dataset, entity), timeout=60).text
        size = bundle_size(html, entity)
        if size:
            sizes[entity] = size
    return sizes, None if sizes else 'SIN_TAMANO_EN_EARTHEXPLORER'


def query(ac, provider, config):
    """Consulta el catálogo del proveedor (CDSE o USGS) con las funciones nativas de ACOLITE.

    Devuelve las fuentes elegibles, la completitud ('COMPLETE', 'INCOMPLETE' o 'UNKNOWN'), los
    contadores del proveedor, el estado de los tamaños y los productos descartados por el perfil
    con su motivo (el proveedor los devuelve porque tocan el rectángulo del AOI, pero no cumplen
    tile/path-row, satélite, intervalo o tipo de producto).
    """
    first, last = instant(config['start']), instant(config['end'])
    cloud = config['cloud']
    sources, unsupported = [], []
    stats, sizes = None, 'OK'
    if provider == 'CDSE':
        _, names, metadata = ac.api.cdse.query(collection='SENTINEL-2', level=1,
            roi=config['limit'], tile=config['search']['tile'], cloud_cover=cloud,
            start_date=(first-timedelta(seconds=1)).replace(tzinfo=None).isoformat(),
            end_date=(last-timedelta(days=1)).replace(tzinfo=None).isoformat(),
            attributes=True, return_metadata=True, verbosity=0)
        for name, meta in zip(names, metadata):
            sources.append({'provider': 'CDSE', 'product': name, 'format': 'SAFE',
                            'id': meta['Id'], 'identity': scene_identity(name), 'metadata': meta})
        # La función nativa sigue @odata.nextLink hasta agotar los resultados.
        completeness = 'COMPLETE'
    else:
        with observe_post('scene-search') as seen:
            result = ac.api.earthexplorer.query(dataset=config['search']['dataset'],
                roi=config['limit'], start_date=first.isoformat(), end_date=last.isoformat(),
                cloud_cover=cloud, attributes=True, verbosity=0)
        if result is None:
            raise RuntimeError('Consulta USGS sin respuesta utilizable')
        entities, names, datasets, metadata = result
        if not len(entities) == len(names) == len(datasets) == len(metadata):
            raise ValueError('Retorno USGS inconsistente')
        for entity, name, dataset, attrs in zip(entities, names, datasets, metadata):
            try:
                info = scene_identity(name)
            except ValueError:
                unsupported.append({'product': name, 'reason': 'producto no soportado: solo Landsat 8/9 L1TP Collection 2 Tier 1'})
                continue
            selected = {m['fieldName']: m['value'] for m in attrs if any(k in m['fieldName'].lower() for k in ['identifier','date','time','cloud','path','row','processing','collection'])}
            sources.append({'provider':'USGS','product':name,'format':'TAR','id':entity,
                            'dataset':dataset,'identity':info,'metadata':selected})
        stats = seen[-1] if seen else None
        completeness = usgs_completeness(stats)
        wanted = [s for s in sources if eligible(s, config)]
        entities = [s['id'] for s in wanted]
        found, error = usgs_sizes(ac, config['search']['dataset'], entities)
        origin = 'M2M'
        if error:
            # download-options exige el rol MACHINE; la página de opciones muestra el mismo bundle.
            found, fallback = earthexplorer_sizes(ac, config['search']['dataset'], entities)
            origin = 'EARTHEXPLORER' if found else 'NO_DISPONIBLE:'+error+','+fallback
        for source in wanted:
            if source['id'] in found:
                source['metadata']['filesize'] = found[source['id']]
        missing = len([s for s in wanted if s['id'] not in found])
        sizes = origin + (f';FALTAN:{missing}' if found and missing else '')
    excluded = unsupported + [{'product': s['product'], 'reason': exclusion(s, config)} for s in sources if not eligible(s, config)]
    return {'sources':[s for s in sources if eligible(s,config)], 'completeness':completeness,
            'provider_counts':stats, 'returned':len(sources)+len(unsupported), 'sizes':sizes,
            'excluded_by_profile':excluded}


def acquire(ac, source, raw):
    """Descarga la escena (o toma el archivo local) y verifica tamaño y checksums.

    Devuelve la ruta del archivo y la fuente con su SHA-256 calculado.
    """
    raw = Path(raw).resolve()
    raw.mkdir(parents=True, exist_ok=True)
    if source.get('local'):
        archive = Path(source['local']).resolve()
    elif source['provider'] == 'CDSE':
        url = f"{ac.config['CDSE_odata']}/Products({source['id']})/$value"
        files = ac.api.cdse.download([url], scenes=[source['product']], output=str(raw),
                                     extract_zip=False, remove_zip=False, override=True, verbosity=0)
        if not files:
            raise RuntimeError('Descarga SAFE fallida')
        archive = Path(files[0])
    else:
        files = ac.api.earthexplorer.download([source['id']], [source['dataset']], [source['product']],
                    output=str(raw), extract_tar=False, remove_tar=False, override=True, verbosity=0)
        if not files:
            raise RuntimeError('Descarga USGS fallida')
        archive = Path(files[0])
    sha = file_hash(archive)
    if source.get('sha256') and sha != source['sha256']:
        raise ValueError('La fuente cambió después de registrarse')
    metadata = source.get('metadata', {})
    if metadata.get('ContentLength') and archive.stat().st_size != metadata['ContentLength']:
        raise ValueError('Descarga incompleta')
    for checksum in metadata.get('Checksum', []):
        algorithm = checksum['Algorithm'].lower().replace('-', '')
        if algorithm in ('md5','sha256') and file_hash(archive, algorithm).lower() != checksum['Value'].lower():
            raise ValueError('Checksum del proveedor no coincide')
    return {'archive':str(archive), 'source':{**source,'sha256':sha}}


def extract(ac, archive, raw, available):
    """Comprueba el ZIP/TAR (espacio, rutas y enlaces) y lo extrae con ACOLITE."""
    root = Path(raw).resolve()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as file:
            entries = [(m.filename, m.file_size, (m.external_attr >> 16) & 0o170000 == 0o120000) for m in file.infolist()]
        types = ['zip']
    else:
        with tarfile.open(archive) as file:
            entries = [(m.name,m.size,not (m.isfile() or m.isdir())) for m in file.getmembers()]
        types = ['tar']
    if not entries or sum(m[1] for m in entries) > available:
        raise ValueError('Archivo vacío o presupuesto de extracción insuficiente')
    for name, _, link in entries:
        if link or not (root/name).resolve().is_relative_to(root):
            raise ValueError('Entrada de archivo insegura')
    bundle, _ = ac.shared.extract_bundle(str(archive), output=str(root), types=types, verbosity=0)
    if not bundle or not Path(bundle).is_dir():
        raise ValueError('No se obtuvo una escena extraída')
    return {'input':str(bundle)}


def process(ac, input_path, settings, output, derive=False):
    """Ejecuta ACOLITE y devuelve las rutas de L1R, L2R y L2W.

    Con `derive=True` parte de un L1R ya alineado y no vuelve a reproyectar ni recortar.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if derive:
        # El L1R retenido ya está alineado. No volver a remuestrear ni recortar.
        overrides = ac.acolite.settings.read(str(settings))
        overrides.update(output_projection=False, reproject_before_ac=False, l1r_crop=False)
        result = ac.acolite.acolite_run(overrides, inputfile=str(input_path), output=str(output))
    else:
        result = ac.acolite.acolite_run(str(settings), inputfile=str(input_path), output=str(output))
    if not result or len(result) != 1:
        raise ValueError('ACOLITE no produjo una escena única')
    record = next(iter(result.values()))
    normalized = {}
    for key in ['l1r','l2r','l2w']:
        value = record.get(key)
        if isinstance(value, list):
            if len(value) != 1:
                raise ValueError('Cantidad de salidas inesperada')
            value = value[0]
        if not value or not Path(value).is_file():
            raise ValueError('Falta salida '+key)
        normalized[key] = value
    return normalized
