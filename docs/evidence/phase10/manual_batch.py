"""Lote manual y secuencial: no constituye el wrapper operativo."""
from pathlib import Path
import subprocess, json
root=Path('/home/antho/projects/oceanos')
evidence=root/'docs/evidence/phase10'
names=[r['name'] for r in json.loads((root/'docs/evidence/phase5/candidates.json').read_text())['candidates'] if '20260804T150719' not in r['name']]
results=[]
for name in names:
    folder=evidence/name.removesuffix('.SAFE');folder.mkdir(exist_ok=True)
    print('INICIO',name,flush=True)
    with (folder/'trial.log').open('w') as log:
        process=subprocess.run(['/home/antho/micromamba/envs/acolite/bin/python','-u',str(root/'.work/phase10_trial.py'),name],stdout=log,stderr=subprocess.STDOUT)
    execution=folder/'execution.json'
    status=json.loads(execution.read_text()).get('status') if execution.exists() else 'sin_reporte'
    results.append({'scene':name,'returncode':process.returncode,'status':status})
    (evidence/'batch_progress.json').write_text(json.dumps(results,indent=2))
    print('FIN',name,status,flush=True)
    if status!='ejecucion_nativa_finalizada': break
