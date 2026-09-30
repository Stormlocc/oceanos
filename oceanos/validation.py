"""Comprobaciones técnicas por bloques; no aprueban calidad científica."""
from pathlib import Path
import netCDF4
import numpy as np


def validate(files, config):
    grid = config['grid']
    dx, dy = grid['pixel_size_xy_m']
    expected_x = np.arange(grid['xrange_m'][0]+dx/2, grid['xrange_m'][1], dx)
    expected_y = np.arange(grid['yrange_m'][0]+dy/2, grid['yrange_m'][1], dy)
    variables = {}
    finite = {}
    for level, path in files.items():
        with netCDF4.Dataset(path) as ds:
            if not np.array_equal(ds['x'][:], expected_x) or not np.array_equal(ds['y'][:], expected_y):
                raise ValueError('La grilla no coincide con el AOI')
            # Verificar CRS, además de ejes: coordenadas iguales no prueban igual proyección.
            crs = [v for v in ds.variables.values() if 'spatial_ref' in v.ncattrs() or 'crs_wkt' in v.ncattrs()]
            from pyproj import CRS
            if not crs or not any(CRS.from_wkt(getattr(v, 'spatial_ref', getattr(v, 'crs_wkt', ''))).to_epsg() == config['epsg'] for v in crs):
                raise ValueError('EPSG no coincide')
            variables[level] = list(ds.variables)
            if level == 'l1r':
                if not str(getattr(ds,'acolite_file_type','')).startswith('L1R') or not any(n.startswith('rhot_') for n in ds.variables):
                    raise ValueError('L1R sin reflectancias TOA o tipo inválido')
            if level == 'l2r':
                if getattr(ds,'acolite_file_type',None) != 'L2R' or not any(n.startswith('rhot_') for n in ds.variables) or not any(n.startswith('rhos_') for n in ds.variables):
                    raise ValueError('L2R sin reflectancias requeridas para flags y productos')
            if level == 'l2w':
                flags = ds.variables.get('l2_flags')
                if flags is None or flags.dtype.kind not in 'iu' or flags.shape != (len(expected_y),len(expected_x)):
                    raise ValueError('Flags ausentes o inválidos')
                for product in config['products']:
                    if product == 'Rrs_*':
                        names = [n for n in ds.variables if n.startswith('Rrs_')]
                    elif product == 'tur_nechad2009':
                        names = [n for n in ds.variables if n.startswith('TUR_Nechad2009_')]
                    else:
                        names = [product] if product in ds.variables else []
                    if not names:
                        raise ValueError('Producto requerido ausente: '+product)
                    for name in names:
                        count = 0
                        for start in range(0,len(expected_y),256):
                            count += int(np.isfinite(np.ma.filled(ds[name][start:start+256,:],np.nan)).sum())
                        finite[name] = {'count':count,'fraction':count/(len(expected_x)*len(expected_y))}
    if 'l2w' in variables and 'Rrs_*' in config['products']:
        expected = {n.replace('rhos_','Rrs_',1) for n in variables['l2r'] if n.startswith('rhos_')}
        if expected != {n for n in variables['l2w'] if n.startswith('Rrs_')}:
            raise ValueError('Rrs_* no contiene todas las bandas rhos')
    return {'technical':'PASSED','scientific':'PENDING','variables':variables,
            'finite_pixels':finite,'grid':grid,'epsg':config['epsg']}
