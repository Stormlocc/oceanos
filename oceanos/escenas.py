"""Etapa "escenas": nubes por zona antes de ACOLITE y exportación del L2W a COG después.

La base guardada de la superimagen es, por zona, sensor y escena, un COG por variable del L2W
(Rrs y productos) más `calidad.tif`, todo en la grilla de la zona y con la tierra en NoData. Con
eso se recalculan sargazo y compuestos sin volver a descargar ni pasar por ACOLITE.
"""
import re
import shutil
from pathlib import Path
import numpy as np
from osgeo import gdal
from .config import digest
from .zonas import grid, rasterize, spatial_reference

gdal.UseExceptions()

# Etiqueta de sensor en carpetas y nombres de archivo de la superimagen.
SENSOR_TAG = {'sentinel2': 'S2', 'landsat': 'Landsat', 'olci': 'OLCI'}
# Bits de l2_flags de ACOLITE (revisión fijada, acolite_flags) que se decodifican en calidad.tif.
FLAG_BITS = {0: 'flag_swir', 1: 'flag_cirrus', 2: 'flag_toa_alto', 3: 'flag_rrs_negativa', 4: 'flag_fuera_escena',
             5: 'flag_mixto'}
QUALITY_BANDS = [*FLAG_BITS.values(), 'rhog_ref', 'residuo_rrs_swir1', 'residuo_rrs_swir2', 'angulo_glint']
# Variables del L2W que no son productos: ejes, coordenadas y flags (van a calidad.tif).
NOT_PRODUCTS = {'x', 'y', 'lat', 'lon', 'l2_flags', 'transverse_mercator', 'crs', 'spatial_ref'}
# COG sin pérdida: ZSTD con predictor (flotante en Float32). Sin overviews: se generan al publicar,
# para no gastar el presupuesto de disco en pirámides que el análisis no usa.
COG_OPTIONS = ['COMPRESS=ZSTD', 'PREDICTOR=YES', 'BLOCKSIZE=512', 'OVERVIEWS=NONE', 'BIGTIFF=IF_SAFER']
# Máscara de tierra: 0 agua de la zona, 1 tierra (con margen), 2 fuera del polígono de la zona.
WATER, LAND, OUTSIDE = 0, 1, 2
# Ventana de ±60 nm para elegir las bandas SWIR del residuo (S2 1614/2202, OLI 1609/2201).
SWIR_REFERENCES, SWIR_TOLERANCE = (1600, 2200), 60


def write_cog(path, bands, zone_grid, data_type=gdal.GDT_Float32, nodata=float('nan'), names=None, metadata=None):
    """Escribe arreglos (filas, columnas) como un COG en la grilla de la zona."""
    rows, columns = zone_grid['shape_yx']
    memory = gdal.GetDriverByName('MEM').Create('', columns, rows, len(bands), data_type)
    memory.SetGeoTransform(zone_grid['geotransform'])
    memory.SetProjection(spatial_reference(zone_grid['epsg']).ExportToWkt())
    for index, array in enumerate(bands, 1):
        band = memory.GetRasterBand(index)
        if nodata is not None:
            band.SetNoDataValue(nodata)
        band.WriteArray(array)
        if names:
            band.SetDescription(names[index-1])
    if metadata:
        memory.SetMetadata({key: str(value) for key, value in metadata.items()})
    gdal.Translate(str(path), memory, format='COG', creationOptions=COG_OPTIONS)
    return Path(path).stat().st_size


def read_band(path, band=1):
    """Lee una banda de un GeoTIFF como arreglo."""
    dataset = gdal.Open(str(path))
    return dataset.GetRasterBand(band).ReadAsArray()


def warped(path, zone_grid, band=1):
    """Una banda de un ráster reproyectada (vecino más cercano) a una grilla; 0 fuera de su extensión."""
    (x0, x1), (y1, y0) = zone_grid['xrange_m'], zone_grid['yrange_m']
    dataset = gdal.Warp('', str(path), format='MEM', dstSRS=f"EPSG:{zone_grid['epsg']}", outputBounds=(x0, y0, x1, y1),
                        xRes=zone_grid['resolution_m'], yRes=zone_grid['resolution_m'], resampleAlg='near',
                        srcBands=[band], dstBands=[1], srcNodata=None, dstNodata=None, warpOptions=['INIT_DEST=0'])
    return dataset.GetRasterBand(1).ReadAsArray()


def provider_masks(input_path, family):
    """Máscaras del producto L1 para medir nubes: (resolución, ráster de nubes, decodificador) o None.

    Sentinel-2: MSK_CLASSI_B00 (banda 1 nubes opacas, 2 cirros, 60 m) y B01 para saber dónde hay
    datos. Landsat: QA_PIXEL (bit 0 relleno; 1 nube dilatada, 2 cirro, 3 nube). OLCI no trae
    una máscara de nubes en el L1: se mide después con los flags de ACOLITE.
    """
    root = Path(input_path)
    if family == 'sentinel2':
        classi = next(root.glob('GRANULE/*/QI_DATA/MSK_CLASSI_B00.jp2'), None)
        coastal = next(root.glob('GRANULE/*/IMG_DATA/*_B01.jp2'), None)
        if classi and coastal:
            return 60, [('classi', classi, 1), ('classi', classi, 2), ('data', coastal, 1)]
    if family == 'landsat':
        quality = next(root.glob('*_QA_PIXEL.TIF'), None)
        if quality:
            return 30, [('qa', quality, 1)]
    return None


def cloud_fraction(input_path, family, zone):
    """Cobertura de datos y nubosidad (%) sobre el polígono de la zona según la máscara del L1, o None."""
    found = provider_masks(input_path, family)
    if not found:
        return None
    resolution, layers = found
    mask_grid = grid(zone['wkt'], zone['epsg'], resolution)
    inside = rasterize(zone['wkt'], mask_grid)
    if family == 'sentinel2':
        bands = {(name, band): warped(path, mask_grid, band) for name, path, band in layers}
        valid = bands[('data', 1)] > 0
        cloud = (bands[('classi', 1)] > 0) | (bands[('classi', 2)] > 0)
    else:
        qa = warped(layers[0][1], mask_grid).astype(np.uint16)
        valid = (qa & 1) == 0
        cloud = (qa & 0b1110) > 0
    seen = valid & inside
    coverage = 100*seen.sum()/inside.sum() if inside.sum() else 0.0
    clouds = 100*(cloud & seen).sum()/seen.sum() if seen.sum() else None
    return {'cobertura_pct': round(float(coverage), 2), 'nubes_pct': None if clouds is None else round(float(clouds), 2),
            'origen': 'MSK_CLASSI_B00' if family == 'sentinel2' else 'QA_PIXEL'}


def wavelength(name):
    """Longitud de onda (nm) al final del nombre de una variable (Rrs_1614 → 1614), o None."""
    match = re.search(r'_(\d{3,4})$', name)
    return int(match[1]) if match else None


def swir_residuals(dataset, names):
    """Rrs más cercana a 1600 y 2200 nm (residuo de glint o espuma tras la corrección); NaN si no hay SWIR."""
    rrs = {wavelength(name): name for name in names if name.startswith('Rrs_') and wavelength(name)}
    shape = dataset['l2_flags'].shape
    result = []
    for reference in SWIR_REFERENCES:
        near = [w for w in rrs if abs(w-reference) <= SWIR_TOLERANCE]
        result.append(variable(dataset, rrs[min(near, key=lambda w: abs(w-reference))]) if near
                      else np.full(shape, np.nan, np.float32))
    return result


def variable(dataset, name):
    """Variable 2D de un NetCDF como Float32, con NaN donde está enmascarada."""
    return np.ma.filled(dataset[name][:].astype(np.float32), np.nan)


def glint_angle(ac, l2r):
    """Ángulo de glint por píxel (grados) con la geometría del L2R y ac.shared.glint_angle de ACOLITE."""
    shape = l2r['l2_flags'].shape if 'l2_flags' in l2r.variables else (len(l2r['y']), len(l2r['x']))
    geometry = {}
    for name in ('sza', 'vza', 'raa'):
        if name in l2r.variables and l2r[name].ndim == 2:
            geometry[name] = variable(l2r, name)
        elif name in l2r.ncattrs():
            geometry[name] = np.full(shape, float(getattr(l2r, name)), np.float32)
        else:
            return np.full(shape, np.nan, np.float32)
    return np.asarray(ac.shared.glint_angle(geometry['sza'], geometry['vza'], geometry['raa']), np.float32)


def quality_layers(ac, l2r, l2w, names):
    """Bandas de calidad.tif: bits de l2_flags, rhog_ref del L2R, residuo Rrs SWIR y ángulo de glint."""
    flags = np.ma.filled(l2w['l2_flags'][:], 0).astype(np.int64)
    layers = [((flags >> bit) & 1).astype(np.float32) for bit in FLAG_BITS]
    rhog = variable(l2r, 'rhog_ref') if 'rhog_ref' in l2r.variables else np.full(flags.shape, np.nan, np.float32)
    return layers + [rhog, *swir_residuals(l2w, names), glint_angle(ac, l2r)]


def staging_for(target):
    """Carpeta de trabajo vacía junto a `target` (`<target>.parcial`).

    Se escribe ahí y se renombra al terminar (`publish`): un corte no deja una carpeta a medias
    que parezca completa.
    """
    staging = Path(target).with_name(Path(target).name+'.parcial')
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    return staging


def publish(staging, target):
    """Reemplaza `target` por la carpeta `staging` ya completa."""
    target = Path(target)
    if target.exists():
        shutil.rmtree(target)
    Path(staging).rename(target)


def export(ac, l2r_path, l2w_path, mask_path, target, zone_grid, metadata):
    """Exporta el L2W de una zona a COG en `target` y devuelve archivos, bytes y estadísticas.

    La tierra y lo que cae fuera de la zona quedan NaN.
    """
    import netCDF4
    staging = staging_for(target)
    land = read_band(mask_path) != WATER
    files = {}
    with netCDF4.Dataset(l2w_path) as l2w, netCDF4.Dataset(l2r_path) as l2r:
        names = [name for name, var in l2w.variables.items()
                 if var.ndim == 2 and name not in NOT_PRODUCTS and var.dtype.kind == 'f']
        if not names:
            raise ValueError('L2W sin variables que exportar')
        for name in names:
            values = variable(l2w, name)
            values[land] = np.nan
            units = getattr(l2w[name], 'units', '')
            files[name+'.tif'] = write_cog(staging/(name+'.tif'), [values], zone_grid, names=[name],
                                           metadata={**metadata, 'variable': name, 'unidades': units})
        quality = quality_layers(ac, l2r, l2w, names)
        for layer in quality:
            layer[land] = np.nan
        files['calidad.tif'] = write_cog(staging/'calidad.tif', quality, zone_grid, names=QUALITY_BANDS,
                                         metadata={**metadata, 'bandas': ','.join(QUALITY_BANDS)})
        stats = scene_stats(quality, ~land)
    publish(staging, target)
    return {'files': files, 'variables': names, 'bytes': sum(files.values()), **stats}


def scene_stats(quality, water):
    """Ángulo de glint medio sobre el agua de la zona y % de agua con nubes según los flags (cirrus o TOA alto)."""
    bands = dict(zip(QUALITY_BANDS, quality))
    seen = water & (bands['flag_fuera_escena'] == 0)
    angle = bands['angulo_glint'][seen]
    clouds = ((bands['flag_cirrus'] == 1) | (bands['flag_toa_alto'] == 1))[seen]
    return {'angulo_glint_deg': round(float(np.nanmean(angle)), 2) if np.isfinite(angle).any() else None,
            'nubes_flags_pct': round(100*float(clouds.mean()), 2) if seen.any() else None,
            'agua_vista_pct': round(100*float(seen.sum())/max(int(water.sum()), 1), 2)}


def verify(target, files):
    """Comprueba que cada COG exportado existe, tiene su tamaño y GDAL lo abre; si no, ValueError."""
    for name, size in files.items():
        path = Path(target)/name
        if not path.is_file() or path.stat().st_size != size or gdal.Open(str(path)) is None:
            raise ValueError('Exportación incompleta: '+name)
    return True


def describe(source, zone_name, family, engine, settings, mask_info):
    """Metadatos que viajan dentro de cada COG (linaje mínimo legible desde ArcGIS o gdalinfo)."""
    return {'escena': source['product'], 'proveedor': source['provider'], 'zona': zone_name, 'sensor': SENSOR_TAG[family],
            'acolite_revision': engine.get('revision', ''), 'mascara_tierra': mask_info,
            'settings_sha256': digest(settings)}
