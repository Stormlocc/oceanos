"""Comprobación técnica mínima de los NetCDF del ensayo; sin validación científica."""
from pathlib import Path
import hashlib, json
import netCDF4
import numpy as np
ROOT = Path('/home/antho/projects/oceanos')
OUTPUT = ROOT/'.work/phase6_20260804/output'
report = {'files': [], 'checks': {}}
coordinates = []
for level in ['L1R','L2R','L2W']:
    files = list(OUTPUT.glob('*_'+level+'.nc'))
    assert len(files)==1, level
    file = files[0]
    with netCDF4.Dataset(file) as ds:
        x, y = ds['x'][:], ds['y'][:]
        coordinates.append((x,y))
        names = list(ds.variables)
        entry = {'level':level,'path':str(file.relative_to(ROOT)), 'bytes':file.stat().st_size,
                 'sha256':hashlib.file_digest(file.open('rb'),'sha256').hexdigest(),
                 'shape_yx':[len(y),len(x)], 'variables':names, 'isodate':ds.isodate,
                 'xrange':ds.xrange.tolist(), 'yrange':ds.yrange.tolist(), 'pixel_size':ds.pixel_size.tolist()}
        assert [len(y),len(x)] == [2440,7335]
        assert np.array_equal(x, np.arange(701985,775330,10))
        assert np.array_equal(y, np.arange(1997355,1972960,-10))
        if level=='L2W':
            required = ['chl_oc3','ndci','fai','ndvi','l2_flags']
            assert all(name in names for name in required), names
            assert any(name.startswith('TUR_Nechad2009_') for name in names)
            rrs = [name for name in names if name.startswith('Rrs_')]
            assert rrs and 'chl_oc4' not in names
            entry['finite_pixels'] = {}
            for name in rrs + required[:-1] + [n for n in names if n.startswith('TUR_Nechad2009_')]:
                count = 0
                for row in range(0,len(y),256):
                    values = np.ma.filled(ds[name][row:row+256,:],np.nan)
                    count += int(np.isfinite(values).sum())
                entry['finite_pixels'][name] = {'count':count,'fraction':count/(len(x)*len(y))}
            report['checks']['productos_obligatorios_presentes'] = True
        report['files'].append(entry)
assert all(np.array_equal(coordinates[0][0],x) and np.array_equal(coordinates[0][1],y) for x,y in coordinates)
report['checks'].update(netcdf_legibles=True,grilla_candidata_confirmada=True,coordenadas_comunes=True)
water = next(f['finite_pixels'] for f in report['files'] if f['level']=='L2W')
report['checks']['productos_acuaticos_con_pixeles_validos'] = all(v['count']>0 for k,v in water.items() if k not in ['fai','ndvi'])
report['eligible_for_scientific_use'] = False  # Requiere fase de validación.
report['cleanup_authorized'] = False
(ROOT/'docs/evidence/phase6/technical_checks.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report['checks']))
