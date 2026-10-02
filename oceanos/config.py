"""Configuración, hashes y exclusión mutua para un único escritor en WSL."""
import contextlib
import fcntl
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import yaml

ROOT = Path(__file__).resolve().parents[1]
REVISION = '80da0c0c681d9597fd4b7737837d6a3e61907b33'
# Instalación activa; prepare aplica el parche de catálogo sobre esta revisión.
ACOLITE = Path.home()/'acolite'
PRODUCTS = {'Rrs_*', 'tur_nechad2009', 'chl_oc3', 'ndci', 'fai', 'ndvi'}
# Settings nativos fijos de OCEANOS. La retención depende del catálogo, nunca de borrado nativo;
# rgb_* evita mapas RGB no solicitados (los GeoTIFF ya están desactivados por defecto).
FIXED = {'delete_extracted_input': 'False', 'l1r_delete_netcdf': 'False',
         'l2r_delete_netcdf': 'False', 'l2w_delete_netcdf': 'False',
         'delete_acolite_run_text_files': 'True', 'rgb_rhot': 'False', 'rgb_rhos': 'False'}


def canonical(value):
    """Serializa a JSON determinista (claves ordenadas, sin espacios)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def digest(value):
    """SHA-256 de la serialización canónica de un valor."""
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path, algorithm='sha256'):
    """Hash de un archivo (SHA-256 por defecto)."""
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def now():
    """Instante actual en UTC, formato ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    """Convierte un texto ISO 8601 a datetime UTC; sin zona horaria se asume UTC."""
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def pair(values):
    """Une valores con comas, como espera ACOLITE en sus settings."""
    return ','.join(str(value) for value in values)


def native_settings(common, selected, landsat, requested):
    """Settings de ACOLITE derivados de los YAML; lo no declarado conserva los defaults de la revisión fijada."""
    limit = common['grid']['limit_south_west_north_east']
    if len(limit) != 4:
        raise ValueError('grid.limit_south_west_north_east requiere sur, oeste, norte, este')
    # Convención ACOLITE: limit S,W,N,E produce un recorte rectangular.
    native = {'region_name': common['aoi']['id'], 'limit': pair(limit),
              'l2w_parameters': ','.join(requested), **FIXED}
    if landsat:
        grid = selected['grid']
        if grid['reproject_stage'] != 'L1R_antes_de_AC':
            raise ValueError('Landsat solo admite reproject_stage L1R_antes_de_AC')
        # Proyectar L1R antes de AC evita que el proyector final descarte l2_flags.
        resolution = grid['output_resolution_m']
        native.update(output_projection='True', reproject_before_ac='True',
                      output_projection_metres='True',
                      output_projection_epsg=str(grid['epsg']),
                      output_projection_resolution=pair([resolution, resolution]),
                      output_projection_xrange=pair(grid['xrange_m']),
                      output_projection_yrange=pair(grid['yrange_m']),
                      output_projection_resolution_align='False',
                      output_projection_resampling_method=grid['resampling'],
                      dsf_tile_dimensions=pair(selected['acolite']['dsf_tile_dimensions']))
    return native


def requested_products(selected, landsat, override=None):
    """Única fuente de productos: --products si se indicó; si no, el YAML del perfil."""
    requested = override or (selected['products'] if landsat else selected['products']['active'])
    # Sin duplicados y en el orden pedido.
    requested = list(dict.fromkeys(product.strip() for product in requested))
    if not requested or '' in requested:
        raise ValueError('Lista de productos vacía o con elementos vacíos')
    unsupported = set(requested) - PRODUCTS
    if unsupported:
        raise ValueError('Productos no soportados (OC4 excluido): ' + ', '.join(sorted(unsupported)))
    if landsat and 'ndci' in requested:
        raise ValueError('NDCI solo está disponible para Sentinel-2')
    return requested


def profile(path, products=None, start=None, end=None):
    """Carga un perfil YAML junto con project.yaml y devuelve la configuración normalizada.

    `products`, `start` y `end` sustituyen a los valores del YAML si se indican.
    """
    path = Path(path).resolve()
    # Abre el AOI/perfil de project.yaml por defecto
    common = yaml.safe_load((path.parent/'project.yaml').read_text())
    # Abre el AOI/perfil de un nuevo .yaml
    selected = yaml.safe_load(path.read_text())
    # Satelite y familia de sensores
    landsat = selected.get('sensor_family') == 'landsat'
    search = selected if landsat else selected['search']
    requested = requested_products(selected, landsat, products)
    # Fechas de inicio y fin del intervalo de búsqueda
    first = instant(start or search['interval_start_utc'])
    last = instant(end or search['interval_end_exclusive_utc'])
    if landsat and any((d.hour,d.minute,d.second,d.microsecond)!=(0,0,0,0) for d in (first,last)):
        raise ValueError('Landsat MVP requiere límites diarios a las 00:00 UTC')
    if first >= last:
        raise ValueError('Intervalo vacío o invertido')
    # Geometría del AOI
    geometry = path.parent/common['aoi']['geometry']
    if file_hash(geometry) != common['aoi']['geometry_sha256']:
        raise ValueError('Cambió el AOI: actualizar su revisión antes de ejecutar, crear un nuevo perfil o usar --start/--end')
    # Settings nativos de ACOLITE generados desde los YAML
    native = native_settings(common, selected, landsat, requested)
    cloud = search['cloud_cover']
    maximum = cloud['maximum_percent'] if cloud['enabled'] else None
    if cloud['enabled'] and (maximum is None or not 0 <= maximum <= 100):
        raise ValueError('Umbral de nubosidad inválido')
    return {'aoi': common['aoi'], 'family': 'landsat' if landsat else 'sentinel2',
            'search': search, 'start': first.isoformat(), 'end': last.isoformat(),
            'cloud': maximum, 'products': sorted(set(requested)), 'native': native,
            'grid': common['grid']['candidate_native_grid'], 'epsg': common['grid']['epsg'],
            'limit': common['grid']['limit_south_west_north_east'],
            'input': common['input'], 'budget': common['storage']['temporary_budget_bytes']}


@contextlib.contextmanager
def exclusive(storage):
    """Bloqueo de archivo: impide que dos procesos OCEANOS escriban en el mismo catálogo."""
    storage = Path(storage).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    with (storage/'.writer.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Ya hay un proceso OCEANOS usando este catálogo') from None
        yield


def disk_bytes(roots):
    """Suma el tamaño de todos los archivos bajo las rutas indicadas."""
    total = 0
    for root in roots:
        if Path(root).exists():
            for path in Path(root).rglob('*'):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
    return total
