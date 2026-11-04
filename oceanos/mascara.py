"""Máscara de tierra fija por zona y grilla, desde ESA WorldCover 10 m (no un umbral de banda).

Una banda que separa tierra y agua cambia con nubes, sedimento, arrecifes someros y sargazo; una
capa externa fija da la misma máscara en todas las fechas. Se rasteriza una vez por zona, sensor
y resolución en storage/superimagen/mascaras/, con un margen hacia el mar para quitar los píxeles
mezcla de la orilla. Valores: 0 agua de la zona, 1 tierra, 2 fuera del polígono de la zona.
"""
import math
import time
from pathlib import Path
import numpy as np
from osgeo import gdal, ogr
from .escenas import LAND, OUTSIDE, SENSOR_TAG, WATER, write_cog
from .zonas import rasterize

gdal.UseExceptions()

# Bucket público de ESA (https://esa-worldcover.org/en/data-access), tiles de 3° × 3° por esquina suroeste.
WORLDCOVER_URL = ('https://esa-worldcover.s3.eu-central-1.amazonaws.com/{version}/{year}/map/'
                  'ESA_WorldCover_10m_{year}_{version}_{tile}_Map.tif')
WORLDCOVER_HOST = 'amazonaws.com'
# Resolución de WorldCover: la máscara se calcula a 10 m y se agrega a la grilla del sensor.
BASE_RESOLUTION = 10


def tile_names(west, south, east, north):
    """Tiles WorldCover (N15W069…) que cubren un rectángulo en grados."""
    names = []
    for lat in range(math.floor(south/3)*3, math.ceil(north/3)*3, 3):
        for lon in range(math.floor(west/3)*3, math.ceil(east/3)*3, 3):
            names.append(f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}")
    return names


def path_for(storage, zone_name, family, resolution):
    """Ruta de la máscara: superimagen/mascaras/tierra_<zona>_<sensor>_<res>m.tif."""
    return Path(storage)/'superimagen'/'mascaras'/f'tierra_{zone_name}_{SENSOR_TAG[family]}_{resolution}m.tif'


def tiles_needed(zones, settings):
    """URLs de los tiles WorldCover que cubren las zonas, por nombre de archivo."""
    names = set()
    for zone in zones.values():
        west, east, south, north = ogr.CreateGeometryFromWkt(zone['wkt']).GetEnvelope()
        names.update(tile_names(west, south, east, north))
    return {Path(url).name: url for url in (WORLDCOVER_URL.format(version=settings['version'], year=settings['year'],
                                                                 tile=name) for name in sorted(names))}


def download(folder, urls, fetch, attempts=3, wait=time.sleep):
    """Descarga los tiles que falten y devuelve sus rutas; ValueError con el tile si no se consigue.

    `fetch` corta una lectura que se queda sin datos (timeout de lectura) y reanuda el `.part`, así
    que reintentar no repite lo ya bajado.
    """
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, url in urls.items():
        target = folder/name
        for attempt in range(attempts):
            if target.is_file():
                break
            try:
                fetch(url, target)
            except Exception as error:
                if attempt+1 == attempts:
                    why = getattr(error, 'reason', None) or type(error).__name__
                    raise ValueError(f'No se pudo descargar {name} de ESA WorldCover tras {attempts} intentos '
                                     f'({why}); repita oceanos mascara') from None
                wait(10*(attempt+1))
        paths.append(target)
    return paths


def land_at_base(tiles, zone_grid, settings):
    """Tierra (bool) a 10 m sobre la misma extensión que la grilla de la zona: toda clase que no sea agua.

    La grilla del sensor está alineada a múltiplos de 10, 30 o 300 m, así que sus límites también
    lo están a 10 m y cada píxel del sensor contiene un bloque entero de píxeles de 10 m.
    """
    (x0, x1), (y1, y0) = zone_grid['xrange_m'], zone_grid['yrange_m']
    mosaic = gdal.BuildVRT('', [str(path) for path in tiles])
    classes = gdal.Warp('', mosaic, format='MEM', dstSRS=f"EPSG:{zone_grid['epsg']}", outputBounds=(x0, y0, x1, y1),
                        xRes=BASE_RESOLUTION, yRes=BASE_RESOLUTION, resampleAlg='near', warpOptions=['INIT_DEST=0']).ReadAsArray()
    return ~np.isin(classes, settings['water_classes'])


def aggregate(land, factor):
    """Agrega tierra de 10 m a una grilla `factor` veces más gruesa: tierra si algún subpíxel lo es."""
    rows, columns = land.shape[0]//factor, land.shape[1]//factor
    return land[:rows*factor, :columns*factor].reshape(rows, factor, columns, factor).any(axis=(1, 3))


def build(tiles, zone, zone_grid, settings):
    """Máscara (0 agua, 1 tierra, 2 fuera) en la grilla de la zona, con el margen hacia el mar."""
    from scipy.ndimage import binary_dilation
    land = aggregate(land_at_base(tiles, zone_grid, settings), zone_grid['resolution_m']//BASE_RESOLUTION)
    if settings['margin_pixels']:
        land = binary_dilation(land, iterations=settings['margin_pixels'])
    mask = np.where(land, LAND, WATER).astype(np.uint8)
    mask[~rasterize(zone['wkt'], zone_grid)] = OUTSIDE
    return mask


def ensure(storage, config, fetch, record=None):
    """Crea las máscaras que falten para las zonas y el sensor del perfil y devuelve {zona: ruta}.

    `fetch(url, destino)` descarga un tile; `record(zona, ruta, info)` registra la máscara en el
    catálogo. Una máscara existente no se recalcula: es fija por zona, sensor y resolución.
    """
    settings = config['superimagen']['land_mask']
    folder = Path(storage)/'auxiliares'/'worldcover'/settings['version']
    version = f"ESA WorldCover {settings['version']} ({settings['year']})"
    paths, tiles = {}, None
    for name, zone in config['zones'].items():
        target = path_for(storage, name, config['family'], config['resolution'])
        if not target.is_file():
            tiles = tiles or download(folder, tiles_needed(config['zones'], settings), fetch)
            target.parent.mkdir(parents=True, exist_ok=True)
            mask = build(tiles, zone, zone['grid'], settings)
            write_cog(target, [mask], zone['grid'], data_type=gdal.GDT_Byte, nodata=None, names=['tierra'],
                      metadata={'fuente': version, 'valores': '0 agua, 1 tierra, 2 fuera de la zona',
                                'margen_pixeles': settings['margin_pixels'],
                                'clases_agua': ','.join(map(str, settings['water_classes']))})
            if record:
                record(name, target, {'capa': version, 'margen_pixeles': settings['margin_pixels'],
                                      'tierra_pct': round(100*float((mask == LAND).sum())/max(int((mask != OUTSIDE).sum()), 1), 2)})
        paths[name] = target
    return paths
