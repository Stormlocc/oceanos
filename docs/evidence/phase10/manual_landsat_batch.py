from pathlib import Path
import subprocess,json,shutil
root=Path('/home/antho/projects/oceanos');evidence=root/'docs/evidence/phase10'
names=['LC08_L1TP_005048_20260809_20260816_02_T1','LC09_L1TP_005048_20260817_20260817_02_T1']
results=[]
for name in names:
 folder=evidence/name;folder.mkdir(exist_ok=True)
 shutil.copy2(root/'config/aoi/lapargera_v1/acolite_l89_candidate.txt',folder/'used_settings.txt')
 print('INICIO',name,flush=True)
 with (folder/'trial.log').open('w') as log:
  process=subprocess.run(['/home/antho/micromamba/envs/acolite/bin/python','-u',str(root/'.work/phase10_landsat_trial.py'),name],stdout=log,stderr=subprocess.STDOUT)
 execution=folder/'execution.json';status=json.loads(execution.read_text()).get('status') if execution.exists() else 'sin_reporte'
 results.append({'scene':name,'returncode':process.returncode,'status':status})
 (evidence/'landsat_batch_progress.json').write_text(json.dumps(results,indent=2))
 print('FIN',name,status,flush=True)
 if status!='ejecucion_nativa_finalizada':break
