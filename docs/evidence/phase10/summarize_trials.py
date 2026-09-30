"""Resumen técnico del lote manual. No sustituye la validación in situ."""
from pathlib import Path
import json,hashlib
import numpy as np,netCDF4
ROOT=Path('/home/antho/projects/oceanos')
EVIDENCE=ROOT/'docs/evidence/phase10'
completed=[ROOT/'docs/evidence/phase6']+[f.parent for f in EVIDENCE.glob('S2*/execution.json') if json.loads(f.read_text()).get('status')=='ejecucion_nativa_finalizada']
previous=EVIDENCE/'technical_summary.json'
rows=json.loads(previous.read_text()) if previous.exists() else []
recorded={row['scene'] for row in rows}
for folder in completed:
    metrics=json.loads((folder/'execution.json').read_text())
    meta=json.loads((folder/'source_metadata.json').read_text())
    if meta['Name'] in recorded: continue  # Resultados anteriores ya comprobados; no se modificaron.
    attrs={a['Name']:a.get('Value') for a in meta['Attributes']}
    row={'scene':meta['Name'],'acquisition_utc':meta['ContentDate']['Start'],'cloud_cover_catalog':attrs.get('cloudCover'),'source_sha256':metrics['source_hashes']['sha256'],'stages_seconds':metrics['stages'],'peak_process_rss_bytes':metrics['peak_self_rss_bytes'],'finite_pixels':{},'artifacts':[],'grid_matches':True,'science_accepted':False}
    coords=[]
    files={f['path'].split('_')[-1].replace('.nc',''):ROOT/f['path'] for f in metrics['outputs']}
    for level in ['L1R','L2R','L2W']:
        file=files[level]
        with netCDF4.Dataset(file) as ds:
            x,y=np.asarray(ds['x'][:]),np.asarray(ds['y'][:])
            row['grid_matches'] &= bool(np.array_equal(x,np.arange(701985,775330,10)) and np.array_equal(y,np.arange(1997355,1972960,-10)))
            names=list(ds.variables)
            if level=='L2R': expected_rrs={n.replace('rhos_','Rrs_',1) for n in names if n.startswith('rhos_')}
            if level=='L2W':
                needed=['chl_oc3','ndci','fai','ndvi','l2_flags']
                row['required_present']=all(n in names for n in needed) and any(n.startswith('TUR_Nechad2009_') for n in names) and bool(expected_rrs) and expected_rrs=={n for n in names if n.startswith('Rrs_')}
                for n in [n for n in names if n.startswith(('Rrs_','TUR_Nechad2009_')) or n in needed[:-1]]:
                    count=0
                    for r in range(0,len(y),256):count+=int(np.isfinite(np.ma.filled(ds[n][r:r+256,:],np.nan)).sum())
                    row['finite_pixels'][n]={'count':count,'fraction':count/(len(y)*len(x))}
                bits={str(b):0 for b in range(7)}
                for r in range(0,len(y),256):
                    flags=np.asarray(ds['l2_flags'][r:r+256,:])
                    for b in range(7):bits[str(b)]+=int(((flags & (1<<b))!=0).sum())
                row['flags_bit_counts']=bits
                row['quality_status']='sin_pixeles_acuaticos_validos' if not any(v['count']>0 for k,v in row['finite_pixels'].items() if k not in ['fai','ndvi']) else 'con_pixeles_acuaticos_pendiente_validacion_cientifica'
        with file.open('rb') as stream: sha=hashlib.file_digest(stream,'sha256').hexdigest()
        row['artifacts'].append({'level':level,'path':str(file.relative_to(ROOT)),'bytes':file.stat().st_size,'sha256':sha})
    rows.append(row)
rows.sort(key=lambda r:r['acquisition_utc'])
(EVIDENCE/'technical_summary.json').write_text(json.dumps(rows,indent=2))
print(json.dumps([{'scene':r['scene'],'grid_matches':r['grid_matches'],'required_present':r['required_present'],'quality':r['quality_status'],'chl_fraction':r['finite_pixels']['chl_oc3']['fraction']} for r in rows],indent=2))
