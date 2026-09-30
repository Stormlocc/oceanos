"""Ensayo manual de fase 10. Delega adquisición y procesamiento en ACOLITE."""
import sys, json, time, hashlib, threading, os, functools, resource
from pathlib import Path
from datetime import datetime, timezone
import requests, subprocess, traceback

ROOT = Path('/home/antho/projects/oceanos')
AC = ROOT / '.work/acolite-audit'
SCENE = sys.argv[1]
assert SCENE.startswith(('LC08_L1TP_', 'LC09_L1TP_')) and '/' not in SCENE
EVIDENCE = ROOT / 'docs/evidence/phase10' / SCENE.removesuffix('.SAFE')
TRIAL = ROOT / '.work/phase10' / SCENE.removesuffix('.SAFE')
RAW = TRIAL / 'raw'
OUTPUT = TRIAL / 'output'
for folder in (RAW, OUTPUT, EVIDENCE): folder.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(AC))
import acolite as ac

metrics = {'scene': SCENE, 'started_at': datetime.now(timezone.utc).isoformat(), 'stages': {}, 'peak_sampled_rss_bytes': 0, 'peak_sampled_disk_bytes': 0, 'sample_seconds': 5}
stop = threading.Event()
def save():
    (EVIDENCE/'execution.json').write_text(json.dumps(metrics, indent=2, default=str))
def disk_bytes():
    return sum(f.stat().st_size for base in (ROOT/'.work/phase6_20260804', ROOT/'.work/phase10', AC/'scratch', AC/'data') for f in base.rglob('*') if f.is_file())
def monitor():
    while not stop.is_set():
        rows = [tuple(map(int,line.split())) for line in subprocess.check_output(['ps','-eo','pid=,ppid=,rss='], text=True, env={**os.environ, 'COLUMNS':'80', 'LINES':'24'}).splitlines()]
        family = {os.getpid()}
        while True:
            children = {pid for pid,parent,rss in rows if parent in family}
            if children.issubset(family): break
            family.update(children)
        rss = sum(rss*1024 for pid,parent,rss in rows if pid in family)
        size = disk_bytes()
        metrics['peak_sampled_rss_bytes'] = max(metrics['peak_sampled_rss_bytes'], rss)
        metrics['peak_sampled_disk_bytes'] = max(metrics['peak_sampled_disk_bytes'], size)
        save()
        if size > 50_000_000_000:
            metrics['status'] = 'detenido_por_presupuesto'; save(); os._exit(2)
        stop.wait(5)
def timed(name, function, *args, **kwargs):
    started = time.monotonic(); print('ETAPA', name, flush=True)
    try: return function(*args, **kwargs)
    finally:
        metrics['stages'][name] = time.monotonic()-started; save()

# Acotar esperas HTTP y capturar solo metadata pública, nunca autenticación.
original_request = requests.Session.request
public_responses = []
def request(session, method, url, **kwargs):
    kwargs.setdefault('timeout', (30, 180))
    response = original_request(session, method, url, **kwargs)
    if 'stac.core.eopf.eodc.eu' in url or ('catalogue.dataspace.copernicus.eu' in url and '/Products?' in url):
        response.raise_for_status()
        public_responses.append({'url': url, 'status': response.status_code, 'body': response.json()})
        (EVIDENCE/'public_queries.json').write_text(json.dumps(public_responses, indent=2))
    return response
requests.Session.request = request
thread = threading.Thread(target=monitor, daemon=True); thread.start()
try:
    source = json.loads((ROOT/'docs/evidence/phase10/landsat_usgs_query.json').read_text())['query_result']
    entities, names, datasets, attributes = source
    idx = names.index(SCENE)
    metadata = {'source':'USGS EarthExplorer', 'entity_id':entities[idx], 'name':SCENE, 'dataset':datasets[idx], 'attributes':attributes[idx]}
    (EVIDENCE/'source_metadata.json').write_text(json.dumps(metadata,indent=2))
    files = timed('descarga', ac.api.earthexplorer.download, [entities[idx]], [datasets[idx]], [SCENE], output=str(RAW), extract_tar=False, remove_tar=False, verbosity=1)
    assert files and len(files)==1, 'No se obtuvo TAR'
    archive=Path(files[0])
    with archive.open('rb') as stream: metrics['source_hashes']={'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
    import tarfile
    with tarfile.open(archive) as bundle_tar:
        members=bundle_tar.getmembers()
        assert members and any(m.name.endswith('_MTL.txt') for m in members), 'TAR sin MTL'
        assert all(not m.issym() and not m.islnk() and (RAW/m.name).resolve().is_relative_to(RAW.resolve()) for m in members)
        metrics['tar_declared_unpacked_bytes']=sum(m.size for m in members)
        assert disk_bytes()+metrics['tar_declared_unpacked_bytes']<50_000_000_000, 'Presupuesto insuficiente'
    bundle, extracted_path=timed('extraccion',ac.shared.extract_bundle,str(archive),output=str(RAW),types=['tar'],verbosity=1)
    assert bundle and Path(bundle).is_dir(), 'Bundle ausente'
    # Medición de etapas nativas sin cambiar sus resultados ni argumentos.
    for module, name in ((ac.acolite,'acolite_l1r'),(ac.output,'project_acolite_netcdf'),(ac.acolite,'acolite_l2r'),(ac.acolite,'acolite_l2w')):
        function = getattr(module,name)
        setattr(module,name, functools.partial(timed,name,function))
    result = timed('procesamiento_total', ac.acolite.acolite_run, str(ROOT/'config/aoi/lapargera_v1/acolite_l89_candidate.txt'), inputfile=bundle, output=str(OUTPUT))
    metrics['native_result'] = result
    metrics['outputs'] = [{'path':str(f.relative_to(ROOT)), 'bytes':f.stat().st_size} for f in OUTPUT.glob('*.nc')]
    metrics['status'] = 'ejecucion_nativa_finalizada'
except Exception as error:
    metrics['status'] = 'fallo'; metrics['error_type'] = type(error).__name__
    metrics['traceback_frames'] = [{'file':frame.filename,'line':frame.lineno,'function':frame.name} for frame in traceback.extract_tb(error.__traceback__)]
    print('ENSAYO DETENIDO:', type(error).__name__, flush=True)
finally:
    stop.set(); thread.join(timeout=6)
    metrics['peak_self_rss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    metrics['finished_at'] = datetime.now(timezone.utc).isoformat()
    save()
