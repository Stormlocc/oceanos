"""Pruebas de contrato de la escena: escala SAFE, continuidad y geolocalización."""
from pathlib import Path
import os,json
import numpy as np
import netCDF4
from pyproj import Transformer
os.environ.setdefault('PROJ_DATA','/home/antho/micromamba/envs/acolite/share/proj')
from osgeo import gdal
ROOT=Path('/home/antho/projects/oceanos')
OUT=ROOT/'.work/phase6_20260804/output'
SAFE=next((ROOT/'.work/phase6_20260804/raw').glob('*.SAFE'))
checks={};details={}
with netCDF4.Dataset(next(OUT.glob('*L1R.nc'))) as l1, netCDF4.Dataset(next(OUT.glob('*L2R.nc'))) as l2:
    for band,wave in [('B02','492'),('B11','1610')]:
        src=next(SAFE.glob('GRANULE/*/IMG_DATA/*_'+band+'.jp2'))
        warped=gdal.Warp('',str(src),format='MEM',dstSRS='EPSG:32619',outputBounds=[701980,1972960,775330,1997360],width=7335,height=2440,resampleAlg='average')
        expected=(warped.ReadAsArray().astype('float32')-1000)/10000
        actual=np.asarray(l1['rhot_'+wave][:]);error=float(np.nanmax(np.abs(expected-actual)))
        checks['escala_'+band]=error==0
        details[band+'_max_abs_error']=error
        del expected,actual,warped
    unchanged=True
    for name in [n for n in l1.variables if n.startswith('rhot_')]:
        for row in range(0,2440,256):
            unchanged &= np.array_equal(l1[name][row:row+256,:],l2[name][row:row+256,:],equal_nan=True)
    checks['toa_conservada_L1R_L2R']=bool(unchanged)
    xx,yy=np.meshgrid(l1['x'][::100],l1['y'][::100])
    lon,lat=Transformer.from_crs(32619,4326,always_xy=True).transform(xx,yy)
    error=max(float(np.max(np.abs(lon-l1['lon'][::100,::100]))),float(np.max(np.abs(lat-l1['lat'][::100,::100]))))
    details['max_error_geolocation_degrees']=error
    checks['geolocalizacion_coherente']=error<1e-5
    swir=np.asarray(l1['rhot_1610'][:]);details['swir_min']=float(np.nanmin(swir))
    checks['todo_swir_supera_umbral']=bool(np.isfinite(swir).all() and (swir>0.0215).all())
with netCDF4.Dataset(next(OUT.glob('*L2W.nc'))) as ds:
    checks['flag_swir_activo_en_todo_el_recorte']=bool(((np.asarray(ds['l2_flags'][:])&1)!=0).all())
report={'checks':checks,'details':details,'scientific_validation':'pendiente_in_situ','water_products_accepted':False}
(ROOT/'docs/evidence/phase7/contract_checks.json').write_text(json.dumps(report,indent=2))
assert all(checks.values()),checks
print(json.dumps(report,indent=2))
