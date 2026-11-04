"""Mapas diarios de sargazo por zona, sensor y día, desde los COG de la etapa escenas.

Por píxel se toma el FAI máximo entre las escenas del día (p. ej. dos tiles que se solapan) y el
NDVI de esa misma escena; `escena_origen` guarda el id del producto de escena elegido
(productos_escena.id). La tierra ya viene en NoData; se descartan además nubes y lo que cae fuera
de la escena según `superimagen.sargassum.discard_flag_bits`. No descarga ni usa ACOLITE.
"""
from pathlib import Path
import numpy as np
from osgeo import gdal
from .bloques import LayerWriter, quality_rows, read_rows, row_blocks
from .config import digest
from .escenas import FLAG_BITS, SENSOR_TAG, publish, staging_for

KIND, METHOD = 'sargazo_diario', 'maximo_fai'
# Cambia la firma de todos los mapas si cambia el método: obliga a recalcularlos.
METHOD_VERSION = 1
VARIABLES = ('fai', 'ndvi')


def flagged(folder, start, count, bits):
    """Píxeles con alguno de los bits de l2_flags indicados (leídos de calidad.tif)."""
    return np.any([quality_rows(folder, start, count, FLAG_BITS[bit]) == 1 for bit in bits], axis=0)


def strongest(stacks, ids):
    """FAI máximo por píxel, NDVI de la misma escena e id de origen (0 donde no hay dato)."""
    fai, ndvi = stacks
    valid = np.isfinite(fai)
    choice = np.argmax(np.where(valid, fai, -np.inf), axis=0)
    seen = valid.any(axis=0)
    pick = lambda stack: np.take_along_axis(stack, choice[None], axis=0)[0]
    best_fai, best_ndvi = pick(fai), pick(ndvi)
    origin = np.asarray(ids, np.int32)[choice]
    best_fai[~seen], best_ndvi[~seen], origin[~seen] = np.nan, np.nan, 0
    return best_fai, best_ndvi, origin


def signature(members, bits):
    """Firma del mapa: productos de entrada (id y fecha de proceso), bits descartados y versión del método."""
    return digest({'productos': [[m['id'], m['fecha_proceso']] for m in members], 'bits': sorted(bits),
                   'version': METHOD_VERSION})


def daily(catalog, config, zone, sensor, date):
    """Calcula (o deja como está) el mapa de un día y devuelve HECHO, AL_DIA o SIN_FAI."""
    storage, aoi = catalog.storage, config['aoi']['id']
    members = [m for m in catalog.products(aoi, zone, sensor, date, date)
               if (storage/m['carpeta']/'fai.tif').is_file()]
    if not members:
        return 'SIN_FAI'
    bits = config['superimagen']['sargassum']['discard_flag_bits']
    firm = signature(members, bits)
    folder = Path('superimagen')/'sargazo'/zone/sensor/'diario'/date
    existing = catalog.composite(KIND, METHOD, aoi, zone, sensor, date)
    if existing and existing['firma'] == firm and (storage/folder).is_dir():
        return 'AL_DIA'
    zone_grid = config['zones'][zone]['grid']
    staging = staging_for(storage/folder)
    meta = {'zona': zone, 'sensor': sensor, 'fecha': date, 'metodo': METHOD, 'escenas': len(members)}
    writers = {'fai': LayerWriter(staging/'fai.tif', zone_grid, name='fai', metadata=meta),
               'ndvi': LayerWriter(staging/'ndvi.tif', zone_grid, name='ndvi', metadata=meta),
               'escena_origen': LayerWriter(staging/'escena_origen.tif', zone_grid, gdal.GDT_Int32, 0,
                                            'escena_origen', {**meta, 'valor': 'productos_escena.id'})}
    seen = 0
    for start, count in row_blocks(zone_grid):
        layers = {name: [] for name in VARIABLES}
        for member in members:
            path = storage/member['carpeta']
            discard = flagged(path, start, count, bits)
            for name in VARIABLES:
                values = read_rows(path/(name+'.tif'), start, count)
                values[discard] = np.nan
                layers[name].append(values)
        stacks = [np.stack(layers[name]) for name in VARIABLES]
        fai, ndvi, origin = strongest(stacks, [m['id'] for m in members])
        seen += int(np.isfinite(fai).sum())
        for name, values in (('fai', fai), ('ndvi', ndvi), ('escena_origen', origin)):
            writers[name].write(start, values)
    size = sum(writer.close() for writer in writers.values())
    publish(staging, storage/folder)
    catalog.record_composite(KIND, METHOD, aoi, zone, sensor, date, str(folder), firm, size,
                             [m['id'] for m in members], {'pixeles_con_fai': seen, 'bits_descartados': bits})
    return 'HECHO'


def update(catalog, config, zones, first, last):
    """Mapas diarios de las zonas y del sensor del perfil con productos en [first, last]; {estado: cantidad}."""
    sensor = SENSOR_TAG[config['family']]
    counts = {}
    for zone, date in catalog.product_dates(config['aoi']['id'], sensor, first, last):
        if zone in zones:
            outcome = daily(catalog, config, zone, sensor, date)
            counts[outcome] = counts.get(outcome, 0)+1
    return counts
