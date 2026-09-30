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
OUTPUT = TRIAL / 'output_grid_v2'
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
    original=json.loads((EVIDENCE/'attempt1_execution.json').read_text())
    metrics['source_hashes']=original['source_hashes']
    bundle=str(next((TRIAL/'output').glob('*_L1R.nc')))
    metrics['reused_l1r']=bundle
    assert Path(bundle).is_file()
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
