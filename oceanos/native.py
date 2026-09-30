"""Adaptación estrecha a las funciones nativas de la revisión auditada."""
import contextlib
import io
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .config import ROOT, REVISION, file_hash, instant


def prepare(path):
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
    revision = subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != REVISION:
        raise ValueError('Revisión ACOLITE inesperada')
    patch = ROOT/'patches/acolite-catalog.patch'
    subprocess.run(['git', '-C', str(path), 'apply', '--reverse', '--check', str(patch)], check=True, capture_output=True)
    # Registrar todos los cambios locales; no atribuirlos al commit upstream.
    diff = subprocess.check_output(['git', '-C', str(path), 'diff', '--binary'])
    import hashlib
    return {'revision': revision, 'patch_sha256': file_hash(patch), 'working_diff_sha256': hashlib.sha256(diff).hexdigest()}


def load(path):
    sys.path.insert(0, str(Path(path).resolve()))
    import acolite
    return acolite


def scene_identity(name):
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


def eligible(source, config):
    info = source['identity']
    if info['family'] != config['family']:
        return False
    raw = info['date']
    from datetime import datetime, timezone
    date = datetime.strptime(raw, '%Y%m%dT%H%M%S' if 'T' in raw else '%Y%m%d').replace(tzinfo=timezone.utc)
    if source.get('metadata', {}).get('ContentDate', {}).get('Start'):
        date = instant(source['metadata']['ContentDate']['Start'])
    # Landsat usa fecha derivada del nombre cuando la API no expone hora normalizada.
    if not instant(config['start']) <= date < instant(config['end']):
        return False
    search = config['search']
    if info['family'] == 'sentinel2':
        return info['tile'] == search['tile'] and info['platform'] in search['platforms']
    return info['path'] == search['wrs_path'] and info['row'] == search['wrs_row']


def query(ac, provider, config):
    first, last = instant(config['start']), instant(config['end'])
    cloud = config['cloud']
    sources = []
    if provider == 'CDSE':
        urls, names, metadata = ac.api.cdse.query(collection='SENTINEL-2', level=1,
            roi=config['limit'], tile=config['search']['tile'], cloud_cover=cloud,
            start_date=(first-timedelta(seconds=1)).replace(tzinfo=None).isoformat(),
            end_date=(last-timedelta(days=1)).replace(tzinfo=None).isoformat(),
            attributes=True, return_metadata=True, verbosity=0)
        for name, meta in zip(names, metadata):
            sources.append({'provider': 'CDSE', 'product': name, 'format': 'SAFE',
                            'id': meta['Id'], 'identity': scene_identity(name), 'metadata': meta})
        completeness = 'COMPLETE'
    elif provider == 'USGS':
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
                continue
            selected = {m['fieldName']: m['value'] for m in attrs if any(k in m['fieldName'].lower() for k in ['identifier','date','time','cloud','path','row','processing','collection'])}
            sources.append({'provider':'USGS','product':name,'format':'TAR','id':entity,
                            'dataset':dataset,'identity':info,'metadata':selected})
        # La función nativa no expone totalHits ni pagina: no afirmar completitud.
        completeness = 'UNKNOWN'
    else:
        features = ac.api.stac.query(limit=config['limit'], start_date=config['start'], end_date=config['end'],
                                    base_url=config['input']['stac_base_url'].rstrip('/'), select_features=False)
        if features is None:
            raise RuntimeError('Consulta STAC sin respuesta utilizable')
        for feature in features:
            name = feature['id']
            try:
                info = scene_identity(name)
            except ValueError:
                continue
            href = feature.get('assets', {}).get('product', {}).get('href', '')
            url = urlsplit(href)
            # No persistir ni recortar silenciosamente credenciales de acceso remoto.
            if url.scheme != 'https' or url.query or url.username or url.fragment:
                continue
            props = feature.get('properties', {})
            if cloud is not None and (props.get('eo:cloud_cover') is None or props['eo:cloud_cover'] > cloud):
                continue
            sources.append({'provider':'STAC','product':name,'format':'ZARR','uri':urlunsplit(url),
                            'identity':info,'metadata':{k:props[k] for k in ['datetime','eo:cloud_cover','processing:version'] if k in props}})
        completeness = 'UNKNOWN'
    return {'sources':[s for s in sources if eligible(s,config)], 'completeness':completeness,
            'normalized_count':len(sources), 'excluded_by_profile':[s['product'] for s in sources if not eligible(s,config)]}


def acquire(ac, source, raw):
    raw = Path(raw).resolve()
    raw.mkdir(parents=True, exist_ok=True)
    if source['format'] == 'ZARR':
        return {'input':source['uri'], 'source':source}
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
    for name, size, link in entries:
        if link or not (root/name).resolve().is_relative_to(root):
            raise ValueError('Entrada de archivo insegura')
    bundle, extracted = ac.shared.extract_bundle(str(archive), output=str(root), types=types, verbosity=0)
    if not bundle or not Path(bundle).is_dir():
        raise ValueError('No se obtuvo una escena extraída')
    return {'input':str(bundle)}


def process(ac, input_path, settings, output, derive=False):
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
