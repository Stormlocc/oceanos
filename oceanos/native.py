"""Adaptación estrecha a las funciones nativas de la revisión auditada."""
import contextlib
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
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


# Resultados por página de scene-search (los mismos 1000 que pide ACOLITE) y tope de páginas.
USGS_PAGE, USGS_PAGES = 1000, 50


def usgs_search(ac, dataset, roi, start, end, cloud, level=1, page=USGS_PAGE):
    """Busca escenas en M2M `scene-search` paginando con startingNumber/nextRecord.

    Reproduce el filtro de ac.api.earthexplorer.query (rectángulo del AOI, intervalo, nubosidad)
    pero sigue `nextRecord` hasta reunir `totalHits`: la nativa pide una sola página de 1000 y
    pierde el resto. Devuelve ([{entity, product, dataset, metadata}], contadores); `product` es
    el 'Landsat Product Identifier L<level>' de la metadata (None si falta).
    """
    import requests
    from osgeo import ogr
    token = ac.api.earthexplorer.auth(netrc_machine='earthexplorer_token')
    if not token:
        raise RuntimeError('Consulta USGS sin token')
    west, east, south, north = ogr.CreateGeometryFromWkt(ac.shared.roi_wkt(roi)).GetEnvelope()
    scene_filter = {'spatialFilter': {'filterType': 'mbr', 'lowerLeft': {'longitude': west, 'latitude': south},
                                      'upperRight': {'longitude': east, 'latitude': north}},
                    'acquisitionFilter': {'start': start, 'end': end}}
    if cloud is not None:
        scene_filter['cloudCoverFilter'] = {'max': cloud, 'min': 0, 'includeUnknown': False}
    found, stats, first = [], {}, 1
    with requests.Session() as session:
        session.headers['X-Auth-Token'] = token
        try:
            for number in range(1, USGS_PAGES+1):
                response = session.post(ac.config['EARTHEXPLORER_api']+'/scene-search', timeout=300, data=json.dumps(
                    {'datasetName': dataset, 'sceneFilter': scene_filter, 'maxResults': page,
                     'startingNumber': first, 'metadataType': 'full'}))
                response.raise_for_status()
                body = response.json()
                data = body.get('data')
                if body.get('errorCode') or data is None:
                    raise ValueError('Consulta USGS fallida')
                results = data.get('results') or []
                for result in results:
                    names = [m['value'] for m in result.get('metadata', [])
                             if 'Product Identifier' in m['fieldName'] and m['fieldName'].endswith(str(level))]
                    found.append({'entity': result['entityId'], 'product': names[0] if names else None,
                                  'dataset': dataset, 'metadata': result.get('metadata', [])})
                stats = {'totalHits': data.get('totalHits'), 'totalHitsAccuracy': data.get('totalHitsAccuracy'),
                         'recordsReturned': len(found), 'pages': number}
                following = data.get('nextRecord')
                if not results or not following or following <= first or len(found) >= (data.get('totalHits') or 0):
                    break
                first = following
        finally:
            with contextlib.suppress(Exception):
                session.post(ac.config['EARTHEXPLORER_api']+'/logout', timeout=30)
    return found, stats


def usgs_completeness(stats):
    """COMPLETE si USGS devolvió todos los resultados, INCOMPLETE si hay más, UNKNOWN sin contadores."""
    if not stats or stats.get('totalHits') is None or stats.get('recordsReturned') is None:
        return 'UNKNOWN'
    if stats['recordsReturned'] < stats['totalHits']:
        # Solo si la paginación se cortó (tope de páginas o respuesta inconsistente de USGS).
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


def bundle_ids(html, entity):
    """(data-entityId, data-productId) del botón 'Download Product' del Product Bundle, o None.

    Es el mismo botón que busca ac.api.earthexplorer.download (clase secondaryDownloadButton).
    """
    for button in re.findall(r'<button\b[^>]*>', html, flags=re.S):
        found = lambda name: re.search(rf'\b{name}="([^"]*)"', button, flags=re.I)
        if (found('title') and found('title')[1] == 'Download Product' and 'secondaryDownloadButton' in button
                and found('data-entityId') and found('data-entityId')[1] == entity and found('data-productId')):
            return found('data-entityId')[1], found('data-productId')[1]
    return None


def eros_login(ac, session):
    """Inicia sesión en EROS como ac.api.earthexplorer.download; devuelve None o un código de fallo."""
    auth = ac.shared.auth('earthexplorer')
    if auth is None:
        return 'SIN_CREDENCIALES_EARTHEXPLORER'
    session.headers['X-Auth-Token'] = f"{ac.api.earthexplorer.auth(netrc_machine='earthexplorer_token')}"
    page = session.get(ac.config['EARTHEXPLORER_ers']+'/login', timeout=60)
    csrf = re.findall(r'name="csrf" value="(.+?)"', page.text)
    if not csrf:
        return 'LOGIN_EARTHEXPLORER'
    session.post(ac.config['EARTHEXPLORER_ers']+'/login', data={'username': auth[0], 'password': auth[1], 'csrf': csrf[0]},
                 allow_redirects=True, timeout=60)
    return None


def earthexplorer_sizes(ac, dataset, entities):
    """Respaldo de usgs_sizes: lee el tamaño de la misma página de opciones que usa la descarga.

    Inicia sesión en EROS; devuelve ({entityId: bytes}, None) o ({}, código). No descarga escenas.
    """
    import requests
    if not entities:
        return {}, None
    session = requests.Session()
    failure = eros_login(ac, session)
    if failure:
        return {}, failure
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
        found, stats = usgs_search(ac, config['search']['dataset'], config['limit'], first.isoformat(),
                                   last.isoformat(), cloud)
        for item in found:
            name, attrs = item['product'] or '', item['metadata']
            try:
                info = scene_identity(name)
            except ValueError:
                unsupported.append({'product': name or item['entity'],
                                    'reason': 'producto no soportado: solo Landsat 8/9 L1TP Collection 2 Tier 1'})
                continue
            selected = {m['fieldName']: m['value'] for m in attrs if any(k in m['fieldName'].lower() for k in ['identifier','date','time','cloud','path','row','processing','collection'])}
            sources.append({'provider':'USGS','product':name,'format':'TAR','id':item['entity'],
                            'dataset':item['dataset'],'identity':info,'metadata':selected})
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


class DownloadError(RuntimeError):
    """Fallo de descarga con un motivo corto y sin datos sensibles (p. ej. HTTP_429, CONEXION)."""
    def __init__(self, reason, retry_after=None):
        super().__init__(reason)
        self.reason, self.retry_after = reason, retry_after


# Bloques de escritura de la descarga en streaming.
CHUNK = 1024*1024


def http_error(response):
    """DownloadError con el código HTTP y, si el proveedor lo indica, los segundos de Retry-After."""
    try:
        wait = int(response.headers.get('Retry-After'))
    except (TypeError, ValueError):
        wait = None
    return DownloadError(f'HTTP_{response.status_code}', wait)


def cdse_token(ac, session):
    """Token de CDSE con las credenciales que usa ACOLITE (máquina `cdse` de ~/.netrc)."""
    auth = ac.shared.auth('cdse')
    if auth is None:
        raise DownloadError('SIN_CREDENCIALES')
    response = session.post(ac.config['CDSE_auth'], timeout=(30, 60), data={
        'client_id': 'cdse-public', 'grant_type': 'password', 'username': auth[0], 'password': auth[1]})
    if not response.ok:
        raise DownloadError(f'TOKEN_HTTP_{response.status_code}')
    token = response.json()
    if 'access_token' not in token:
        raise DownloadError('TOKEN_SIN_ACCESO')
    return token


def cdse_logout(ac, session, token):
    """Cierra la sesión del token: CDSE admite 100 sesiones activas por usuario y cada token abre una."""
    with contextlib.suppress(Exception):
        session.post(ac.config['CDSE_auth'].rsplit('/token', 1)[0]+'/logout', timeout=30,
                     data={'client_id': 'cdse-public', 'refresh_token': token.get('refresh_token', '')})


def trusted_host(url, domain):
    """Indica si el host de `url` es `domain` o un subdominio suyo."""
    host = urlparse(url).hostname or ''
    return host == domain or host.endswith('.'+domain)


def trusted_get(session, url, trusted, headers=None):
    """GET en streaming que sigue a mano hasta 5 redirecciones, solo hacia hosts de `trusted`.

    requests quita las cabeceras de autorización al cambiar de host; seguirlas a mano conserva el
    token y la cabecera Range, y permite rechazar un host ajeno o bajar de https a http.
    """
    scheme = urlparse(url).scheme
    response = session.get(url, stream=True, allow_redirects=False, timeout=(30, 120), headers=headers)
    for _ in range(5):
        if response.status_code not in (301, 302, 303, 307, 308):
            return response
        response.close()
        url = urljoin(url, response.headers.get('Location', ''))
        if urlparse(url).scheme != scheme or not trusted_host(url, trusted):
            raise DownloadError('REDIRECCION_NO_CONFIABLE')
        response = session.get(url, stream=True, allow_redirects=False, timeout=(30, 120), headers=headers)
    return response


def content_range(response):
    """(inicio, total) de la cabecera Content-Range de una respuesta 206, o None si no se entiende."""
    match = re.fullmatch(r'bytes (\d+)-\d+/(\d+|\*)', response.headers.get('Content-Range', '').strip())
    return (int(match[1]), None if match[2] == '*' else int(match[2])) if match else None


def fetch(session, url, target, trusted, fresh=False):
    """Descarga `url` en streaming a `target` y devuelve {md5, sha256}; reanuda un `.part` previo.

    Si un intento anterior dejó `<target>.part` y su `.part.json` (ETag o Last-Modified y tamaño
    total del primer intento), pide solo lo que falta con `Range` e `If-Range`: el servidor manda
    el resto (206) solo si el archivo no cambió; si responde el archivo completo (200) o un rango
    que no empieza donde quedó el `.part`, se empieza de cero. Sin validador no se reanuda, para
    no unir pedazos de dos archivos distintos. Los hashes cubren el archivo completo (incluida la
    parte ya escrita) y se comprueba que llegaron todos los bytes anunciados. `fresh` indica que ya
    se descartó lo parcial: un 206 o 416 sin haber pedido rango es un fallo (RANGO_INVALIDO).
    """
    import requests
    part, meta = target.with_name(target.name+'.part'), target.with_name(target.name+'.part.json')
    saved = {}
    with contextlib.suppress(OSError, ValueError):
        saved = json.loads(meta.read_text())
    offset = part.stat().st_size if part.is_file() and (saved.get('etag') or saved.get('modified')) else 0
    try:
        headers = {'Range': f'bytes={offset}-', 'If-Range': saved.get('etag') or saved['modified']} if offset else None
        response = trusted_get(session, url, trusted, headers)
        with response:
            resumed = response.status_code == 206 and offset and content_range(response)
            if resumed and (resumed[0] != offset or (saved.get('total') and resumed[1] not in (None, saved['total']))):
                resumed = None
            if (response.status_code == 206 and not resumed) or response.status_code == 416:
                if fresh or not offset:
                    raise DownloadError('RANGO_INVALIDO')
                # Rango distinto del pedido: se descarta lo parcial y se pide entero.
                response.close()
                return fetch_again(session, url, target, trusted, part, meta)
            if response.status_code not in (200, 206):
                raise http_error(response)
            digests = {'md5': hashlib.md5(), 'sha256': hashlib.sha256()}
            if resumed:
                total = resumed[1] or saved.get('total')
                with part.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(CHUNK), b''):
                        for value in digests.values():
                            value.update(chunk)
            else:
                offset = 0
                length = response.headers.get('Content-Length')
                total = int(length) if length and length.isdigit() else None
                meta.write_text(json.dumps({'etag': response.headers.get('ETag'),
                                            'modified': response.headers.get('Last-Modified'), 'total': total}))
            written = offset
            with part.open('ab' if resumed else 'wb') as stream:
                for chunk in response.iter_content(CHUNK):
                    stream.write(chunk)
                    written += len(chunk)
                    for value in digests.values():
                        value.update(chunk)
    except requests.Timeout:
        raise DownloadError('TIEMPO_AGOTADO') from None
    except requests.RequestException:
        raise DownloadError('CONEXION') from None
    if total is not None and written != total:
        # Conexión cerrada antes de tiempo sin error de la librería: el .part queda para reanudar.
        raise DownloadError('CONEXION')
    part.replace(target)
    meta.unlink(missing_ok=True)
    return {name: value.hexdigest() for name, value in digests.items()}


def fetch_again(session, url, target, trusted, part, meta):
    """Descarta el `.part` y su `.part.json` y descarga el archivo entero."""
    part.unlink(missing_ok=True)
    meta.unlink(missing_ok=True)
    return fetch(session, url, target, trusted, fresh=True)


def cdse_download(ac, source, raw):
    """Descarga el ZIP de un producto CDSE en streaming a disco y devuelve (ruta, {md5, sha256}).

    Reemplaza a ac.api.cdse.download, que pide el archivo dos veces y lo acumula en memoria. Sigue
    las redirecciones a mano solo hacia hosts del dominio de CDSE y calcula los hashes mientras
    escribe. Si se corta queda el `.part`, que el siguiente intento reanuda (ver `fetch`).
    """
    import requests
    target = Path(raw)/(source['product'].split('.')[0]+'.zip')
    url = f"{ac.config['CDSE_odata']}/Products({source['id']})/$value"
    # Solo hosts del dominio del catálogo (dataspace.copernicus.eu) y sin bajar de https a http.
    trusted = urlparse(url).hostname.split('.', 1)[1]
    with requests.Session() as session:
        token = cdse_token(ac, session)
        session.headers['Authorization'] = 'Bearer '+token['access_token']
        try:
            digests = fetch(session, url, target, trusted)
        finally:
            cdse_logout(ac, session, token)
    return target, digests


# Hosts aceptados para la descarga USGS (earthexplorer.usgs.gov, landsatlook.usgs.gov, dds.cr.usgs.gov…).
USGS_DOMAIN = 'usgs.gov'


def usgs_download(ac, source, raw):
    """Descarga el TAR (Product Bundle L1) de una escena Landsat en streaming y devuelve (ruta, {md5, sha256}).

    Sigue los pasos de ac.api.earthexplorer.download (sesión EROS, botón 'Download Product' de la
    página de opciones y URL de descarga de /download/<producto>/<entidad>/EE/), pero escribe a
    disco mientras recibe: la nativa pide el archivo dos veces y lo acumula en memoria (≈3,3 GB
    de RAM). Si se corta queda el `.part`, que el siguiente intento reanuda (ver `fetch`).
    """
    import requests
    target = Path(raw)/(source['product']+'.tar')
    with requests.Session() as session:
        try:
            failure = eros_login(ac, session)
            if failure:
                raise DownloadError('SIN_CREDENCIALES' if failure.startswith('SIN_CREDENCIALES') else failure)
            try:
                page = session.get('{}/options/{}/{}'.format(ac.config['EARTHEXPLORER_download'], source['dataset'],
                                                             source['id']), timeout=60)
                ids = bundle_ids(page.text, source['id'])
                if not ids:
                    raise DownloadError('SIN_BOTON_DESCARGA')
                response = session.get('{}/{}/{}/EE/'.format(ac.config['EARTHEXPLORER_download'], ids[1], ids[0]),
                                       allow_redirects=False, timeout=120)
                if not response.ok:
                    raise DownloadError('SIN_URL_DESCARGA')
                try:
                    url = response.json()['url']
                except (ValueError, KeyError, TypeError):
                    raise DownloadError('SIN_URL_DESCARGA') from None
                # Mismo esquema que EarthExplorer (https) y un host de USGS.
                if urlparse(url).scheme != urlparse(ac.config['EARTHEXPLORER_download']).scheme \
                        or not trusted_host(url, USGS_DOMAIN):
                    raise DownloadError('REDIRECCION_NO_CONFIABLE')
            except requests.Timeout:
                raise DownloadError('TIEMPO_AGOTADO') from None
            except requests.RequestException:
                raise DownloadError('CONEXION') from None
            digests = fetch(session, url, target, USGS_DOMAIN)
        finally:
            with contextlib.suppress(Exception):
                session.post(ac.config['EARTHEXPLORER_ers']+'/logout', timeout=30)
    return target, digests


def acquire(ac, source, raw):
    """Descarga la escena (o toma el archivo local) y verifica tamaño y checksums.

    Devuelve la ruta del archivo y la fuente con su SHA-256 calculado.
    """
    raw = Path(raw).resolve()
    raw.mkdir(parents=True, exist_ok=True)
    digests = {}
    if source.get('local'):
        archive = Path(source['local']).resolve()
    elif source['provider'] == 'CDSE':
        archive, digests = cdse_download(ac, source, raw)
    else:
        archive, digests = usgs_download(ac, source, raw)
    sha = digests.get('sha256') or file_hash(archive)
    if source.get('sha256') and sha != source['sha256']:
        raise ValueError('La fuente cambió después de registrarse')
    metadata = source.get('metadata', {})
    if metadata.get('ContentLength') and archive.stat().st_size != metadata['ContentLength']:
        raise ValueError('Descarga incompleta')
    for checksum in metadata.get('Checksum', []):
        algorithm = checksum['Algorithm'].lower().replace('-', '')
        if algorithm in ('md5','sha256') and (digests.get(algorithm) or file_hash(archive, algorithm)).lower() != checksum['Value'].lower():
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
