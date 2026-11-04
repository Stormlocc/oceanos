"""Comprobaciones técnicas por bloques; no aprueban calidad científica."""
import netCDF4
import numpy as np
from pyproj import CRS
from .zonas import axes


def product_variables(product, names):
    """Variables del L2W que corresponden a un producto pedido en l2w_parameters.

    `Rrs_*` → todas las Rrs_<λ>; `tur_nechad2009` → TUR_Nechad2009_<λ>; el resto por nombre exacto
    o con sufijo de onda (`chl_re_gons` → chl_re_gons). La comparación no distingue mayúsculas, y
    `fai` no toma `fait`: el sufijo debe empezar con '_'.
    """
    stem = product.rstrip('*').rstrip('_').lower()
    return [name for name in names if name.lower() == stem or name.lower().startswith(stem+'_')]


def check_grid(dataset, zone_grid):
    """ValueError si los ejes o el EPSG del NetCDF no son los de la grilla de la zona."""
    expected_x, expected_y = axes(zone_grid)
    if not np.allclose(dataset['x'][:], expected_x) or not np.allclose(dataset['y'][:], expected_y):
        raise ValueError('La grilla no coincide con la zona')
    # Coordenadas iguales no prueban igual proyección: verificar también el CRS.
    crs = [v for v in dataset.variables.values() if 'spatial_ref' in v.ncattrs() or 'crs_wkt' in v.ncattrs()]
    if not any(CRS.from_wkt(getattr(v, 'spatial_ref', getattr(v, 'crs_wkt', ''))).to_epsg() == zone_grid['epsg'] for v in crs):
        raise ValueError('EPSG no coincide con la zona')


def finite_pixels(variable, rows):
    """Píxeles finitos de una variable 2D, leída por bloques de 256 filas."""
    return sum(int(np.isfinite(np.ma.filled(variable[start:start+256, :], np.nan)).sum()) for start in range(0, rows, 256))


def validate(files, zone_grid, products):
    """Valida grilla, EPSG, variables y productos de L1R/L2R/L2W de una zona y cuenta píxeles finitos."""
    rows, columns = zone_grid['shape_yx']
    variables, finite = {}, {}
    for level, path in files.items():
        with netCDF4.Dataset(path) as ds:
            check_grid(ds, zone_grid)
            variables[level] = list(ds.variables)
            if level == 'l1r':
                if not str(getattr(ds, 'acolite_file_type', '')).startswith('L1R') or not any(n.startswith('rhot_') for n in ds.variables):
                    raise ValueError('L1R sin reflectancias TOA o tipo inválido')
            if level == 'l2r':
                if getattr(ds, 'acolite_file_type', None) != 'L2R' or not any(n.startswith('rhos_') for n in ds.variables):
                    raise ValueError('L2R sin reflectancias requeridas para flags y productos')
            if level == 'l2w':
                flags = ds.variables.get('l2_flags')
                if flags is None or flags.dtype.kind not in 'iu' or flags.shape != (rows, columns):
                    raise ValueError('Flags ausentes o inválidos')
                for product in products:
                    names = product_variables(product, ds.variables)
                    if not names:
                        raise ValueError('Producto requerido ausente: '+product)
                    for name in names:
                        count = finite_pixels(ds[name], rows)
                        finite[name] = {'count': count, 'fraction': count/(rows*columns)}
    if 'l2w' in variables and 'l2r' in variables and 'Rrs_*' in products:
        expected = {n.replace('rhos_', 'Rrs_', 1) for n in variables['l2r'] if n.startswith('rhos_')}
        if expected != {n for n in variables['l2w'] if n.startswith('Rrs_')}:
            raise ValueError('Rrs_* no contiene todas las bandas rhos')
    return {'technical': 'PASSED', 'scientific': 'PENDING', 'finite_pixels': finite, 'grid': zone_grid}
