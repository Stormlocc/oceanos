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
# Perfil por defecto: AOI Water2Coast.
PROFILE = ROOT/'config/aoi/water2coast_v1'
SENSORS = ('sentinel2', 'landsat', 'olci')
PLATFORMS = {'sentinel2': ('S2A', 'S2B', 'S2C'), 'landsat': ('L8', 'L9'), 'olci': ('S3A', 'S3B')}
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


def setting(value):
    """Valor de setting ACOLITE como texto (booleanos con mayúscula inicial, listas con comas)."""
    if isinstance(value, bool):
        return str(value)
    return pair(value) if isinstance(value, (list, tuple)) else str(value)


def zone_settings(zone, grid, common, products):
    """Settings de ACOLITE de una zona: recorte, productos, glint y proyección del L1R a la grilla de la zona.

    Proyectar el L1R antes de la corrección (`reproject_before_ac`) deja L1R, L2R y L2W en la
    grilla de la zona y conserva l2_flags, que el proyector final de ACOLITE no escribe. Con la
    grilla alineada a la resolución nativa y `nearest`, en Sentinel-2 y Landsat es un recorte sin
    mezclar píxeles. Lo no declarado conserva el default de la revisión fijada.
    """
    from .zonas import limit
    native = {'region_name': zone, 'limit': pair(limit(grid)), 'l2w_parameters': ','.join(products), **FIXED,
              'output_projection': 'True', 'reproject_before_ac': 'True', 'output_projection_metres': 'True',
              'output_projection_epsg': str(grid['epsg']),
              'output_projection_resolution': pair([grid['resolution_m']]*2),
              'output_projection_xrange': pair(grid['xrange_m']), 'output_projection_yrange': pair(grid['yrange_m']),
              # Los rangos ya están alineados: con True ACOLITE los realinea y cambia la forma en un píxel.
              'output_projection_resolution_align': 'False', 'output_projection_resampling_method': 'nearest'}
    native.update({key: setting(value) for key, value in (common.get('acolite') or {}).items()})
    return native


def requested_products(selected, override=None):
    """Productos del sensor: --products (subconjunto del perfil) o la lista del YAML, sin duplicados."""
    available = list(dict.fromkeys(selected['products']))
    requested = list(dict.fromkeys(product.strip() for product in override)) if override else available
    if not requested or '' in requested:
        raise ValueError('Lista de productos vacía o con elementos vacíos')
    foreign = [product for product in requested if product not in available]
    if foreign:
        raise ValueError(f"Productos no disponibles para {selected['sensor_family']}: {', '.join(foreign)}; "
                         f"opciones: {', '.join(available)}")
    return requested


def chosen(values, available, label):
    """Restringe una lista del perfil a los valores pedidos; error si se pide algo ajeno."""
    if not values:
        return list(available)
    foreign = [value for value in values if value not in available]
    if foreign:
        raise ValueError(f"{label} {', '.join(foreign)} no disponible; opciones: {', '.join(available)}")
    return [value for value in available if value in values]


def search_places(selected, zones):
    """Tiles (S2) o path/row (Landsat) de las zonas elegidas; OLCI no usa ninguno."""
    places = selected.get('tiles') or selected.get('path_rows') or {}
    return sorted({place for zone in zones for place in places.get(zone, [])})


def union_limit(limits):
    """Rectángulo (sur, oeste, norte, este) que contiene los `limit` de todas las zonas."""
    return [min(l[0] for l in limits), min(l[1] for l in limits), max(l[2] for l in limits), max(l[3] for l in limits)]


def profile_sensors(directory=PROFILE):
    """Sensores del perfil en el orden en que `run` los procesa."""
    return list(yaml.safe_load((Path(directory)/'project.yaml').read_text())['sensors'])


def profile(directory=PROFILE, sensor='sentinel2', products=None, start=None, end=None, satellites=None, zones=None):
    """Carga project.yaml y el perfil del sensor y devuelve la configuración normalizada.

    `products`, `start` y `end` sustituyen a los valores del YAML; `satellites` y `zones`
    restringen las plataformas y las zonas del perfil. Comprueba el SHA-256 del AOI.
    """
    from .zonas import grid, read_zones
    directory = Path(directory).resolve()
    common = yaml.safe_load((directory/'project.yaml').read_text())
    if sensor not in common['sensors']:
        raise ValueError(f"Sensor {sensor} no disponible en el perfil; opciones: {', '.join(common['sensors'])}")
    selected = yaml.safe_load((directory/common['sensors'][sensor]).read_text())
    geometry = directory/common['aoi']['geometry']
    if file_hash(geometry) != common['aoi']['geometry_sha256']:
        raise ValueError('Cambió el AOI: actualizar su revisión antes de ejecutar o crear un nuevo perfil')
    first = instant(start or selected['interval_start_utc'])
    last = instant(end or selected['interval_end_exclusive_utc'])
    if first >= last:
        raise ValueError('Intervalo vacío o invertido')
    if sensor == 'landsat' and any((d.hour, d.minute, d.second, d.microsecond) != (0, 0, 0, 0) for d in (first, last)):
        raise ValueError('Landsat requiere límites diarios a las 00:00 UTC')
    requested = requested_products(selected, products)
    shapes = read_zones(geometry, common['aoi']['name_field'])
    names = chosen(zones, list(common['zones']), 'Zona')
    resolution = selected['resolution_m']
    configured = {}
    for name in names:
        zone = common['zones'][name]
        if zone['name'] not in shapes:
            raise ValueError(f"La zona {zone['name']} no está en {geometry.name}")
        zone_grid = grid(shapes[zone['name']], zone['epsg'], resolution)
        configured[name] = {'name': zone['name'], 'epsg': zone['epsg'], 'wkt': shapes[zone['name']], 'grid': zone_grid,
                            'native': zone_settings(name, zone_grid, common, requested),
                            'places': (selected.get('tiles') or selected.get('path_rows') or {}).get(name)}
    search = {**{k: v for k, v in selected.items() if k not in ('products', 'tiles', 'path_rows')},
              'platforms': chosen(satellites, selected['platforms'], 'Satélite'), 'places': search_places(selected, names)}
    return {'aoi': common['aoi'], 'family': sensor, 'profile': str(directory), 'search': search,
            'start': first.isoformat(), 'end': last.isoformat(), 'products': requested, 'resolution': resolution,
            'zones': configured,
            'limit': union_limit([[float(v) for v in z['native']['limit'].split(',')] for z in configured.values()]),
            'cloud_zone_max': common['cloud_cover']['maximum_percent_per_zone'], 'input': common['input'],
            'budget': common['storage']['temporary_budget_bytes'],
            'superimagen_budget': common['storage']['superimagen_budget_bytes'],
            'superimagen': common['superimagen'], 'sensors': list(common['sensors'])}


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


def received_bytes(pid='self'):
    """Bytes leídos por un proceso (archivos y red) según /proc/<pid>/io; None si no se puede leer."""
    try:
        with open(f'/proc/{pid}/io') as stream:
            for line in stream:
                if line.startswith('rchar:'):
                    return int(line.split()[1])
    except (OSError, ValueError):
        return None
    return None


def disk_bytes(roots):
    """Suma el tamaño de todos los archivos bajo las rutas indicadas."""
    total = 0
    for root in roots:
        if Path(root).exists():
            for path in Path(root).rglob('*'):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
    return total
