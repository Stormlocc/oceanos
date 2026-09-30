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
PRODUCTS = {'Rrs_*', 'tur_nechad2009', 'chl_oc3', 'ndci', 'fai', 'ndvi'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path, algorithm='sha256'):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, algorithm).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def instant(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def settings(path):
    result = {}
    for line in Path(path).read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            key, value = line.split('=', 1)
            result[key.strip()] = value.strip()
    return result


def profile(path, products=None, start=None, end=None):
    path = Path(path).resolve()
    common = yaml.safe_load((path.parent/'project.yaml').read_text())
    selected = yaml.safe_load(path.read_text())
    landsat = selected.get('sensor_family') == 'landsat'
    search = selected if landsat else selected['search']
    requested = products or (selected['products'] if landsat else selected['products']['active'])
    if not requested or set(requested) - PRODUCTS or (landsat and 'ndci' in requested):
        raise ValueError('Productos no soportados; OC4 excluido y NDCI solo Sentinel-2')
    first = instant(start or search['interval_start_utc'])
    last = instant(end or search['interval_end_exclusive_utc'])
    if landsat and any((d.hour,d.minute,d.second,d.microsecond)!=(0,0,0,0) for d in (first,last)):
        raise ValueError('Landsat MVP requiere límites diarios a las 00:00 UTC')
    if first >= last:
        raise ValueError('Intervalo vacío o invertido')
    geometry = path.parent/common['aoi']['geometry']
    if file_hash(geometry) != common['aoi']['geometry_sha256']:
        raise ValueError('Cambió el AOI: actualizar su revisión antes de ejecutar')
    native = settings(path.parent/(selected['settings_file'] if landsat else selected['acolite']['settings_file']))
    native['l2w_parameters'] = ','.join(requested)
    # La retención depende del catálogo, nunca de borrado implícito nativo.
    for key in ['delete_extracted_input', 'l1r_delete_netcdf', 'l2r_delete_netcdf', 'l2w_delete_netcdf']:
        native[key] = 'False'
    native['delete_acolite_run_text_files'] = 'True'
    cloud = search['cloud_cover']
    maximum = cloud['maximum_percent'] if cloud['enabled'] else None
    if cloud['enabled'] and (maximum is None or not 0 <= maximum <= 100):
        raise ValueError('Umbral de nubosidad inválido')
    return {'aoi': common['aoi'], 'family': 'landsat' if landsat else 'sentinel2',
            'search': search, 'start': first.isoformat(), 'end': last.isoformat(),
            'cloud': maximum, 'products': sorted(set(requested)), 'native': native,
            'grid': common['grid']['candidate_native_grid'], 'epsg': common['grid']['epsg'],
            'limit': common['grid']['limit_south_west_north_east'],
            'input': common['input'], 'budget': common['storage']['temporary_budget_bytes'],
            'acolite_revision': common['acolite']['git_sha']}


@contextlib.contextmanager
def exclusive(storage):
    storage = Path(storage).resolve()
    storage.mkdir(parents=True, exist_ok=True)
    with (storage/'.writer.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Ya hay un proceso OCEANOS usando este catálogo') from None
        yield


def disk_bytes(roots):
    total = 0
    for root in roots:
        if Path(root).exists():
            for path in Path(root).rglob('*'):
                if path.is_file() and not path.is_symlink():
                    total += path.stat().st_size
    return total
