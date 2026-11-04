"""Compuestos de calidad de agua por zona y sensor, desde los COG de la etapa escenas.

Mensual: las escenas de un mismo día se reducen primero a una observación por píxel (la de menor
glint), para que dos tiles solapados de la misma pasada no cuenten doble; después se combinan los
días con dos métodos:

- mejor_pixel (a): gana la observación de menor glint (`rhog_ref`; en OLCI, mayor ángulo de glint).
- media_ponderada (b): media con peso por glint: 1 hasta `full_weight_max`, lineal hasta 0 en
  `discard_above`; lo que pasa de ese umbral no entra.

En ambos se descartan los píxeles que ACOLITE no corrigió (`rhog_ref` NaN, que ACOLITE deja donde
rhos(1600) > glint_mask_rhos_threshold, o el residuo SWIR por encima de ese umbral), los bits de
l2_flags de `superimagen.composite` y, en OLCI, el ángulo de glint bajo el mínimo.

Cada compuesto guarda además `fecha_origen` (AAAAMMDD), `n_observaciones` y la medida de glint de
la observación elegida (a) o `peso_total` (b): con eso, estaciones y años se calculan desde los
mensuales sin volver a las escenas.
"""
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from osgeo import gdal
from .bloques import LayerWriter, quality_rows, read_rows, row_blocks
from .config import digest
from .escenas import FLAG_BITS, SENSOR_TAG, publish, staging_for, wavelength

MONTHLY, SEASONAL, ANNUAL = 'mensual', 'estacional', 'anual'
BEST, WEIGHTED = 'mejor_pixel', 'media_ponderada'
METHODS = (BEST, WEIGHTED)
SEASONS = {'DEF': (12, 1, 2), 'MAM': (3, 4, 5), 'JJA': (6, 7, 8), 'SON': (9, 10, 11)}
# Cambia la firma de todos los compuestos si cambia el método: obliga a recalcularlos.
METHOD_VERSION = 1
# Bandas equivalentes entre satélites gemelos (S2A 665 nm, S2B 664 nm): mismo nombre de salida.
WAVELENGTH_TOLERANCE = 10
# Capas propias del compuesto (no son variables del L2W).
LAYERS = ('calidad', 'fecha_origen', 'n_observaciones', 'rhog_ref', 'angulo_glint', 'peso_total')


def glint_weight(rhog, settings):
    """Peso por glint: 1 hasta full_weight_max, lineal hasta 0 en discard_above; 0 sin dato."""
    full, discard = settings['full_weight_max'], settings['discard_above']
    weight = np.clip((discard-rhog)/(discard-full), 0, 1)
    return np.where(np.isfinite(rhog), weight, 0).astype(np.float32)


def glint_layer(family):
    """Nombre de la medida de glint que guarda el mejor píxel: ángulo en OLCI, rhog_ref en el resto."""
    return 'angulo_glint' if family == 'olci' else 'rhog_ref'


def scene_glint(folder, start, count, family, settings, bits):
    """Métrica de glint (menor es mejor; inf si no vale) y peso de una escena en un bloque de filas."""
    discard = np.any([quality_rows(folder, start, count, FLAG_BITS[bit]) == 1 for bit in bits], axis=0)
    if family == 'olci':
        angle = quality_rows(folder, start, count, 'angulo_glint')
        valid = ~discard & (angle >= settings['minimum_glint_angle_deg'])
        metric, weight = -angle, np.ones_like(angle)
    else:
        rhog = quality_rows(folder, start, count, 'rhog_ref')
        # calidad.tif guarda el residuo como Rrs; ACOLITE enmascara por rhos = π·Rrs.
        rhos_swir = np.pi*quality_rows(folder, start, count, 'residuo_rrs_swir1')
        valid = ~discard & np.isfinite(rhog) & ~(rhos_swir > settings['rhos_mask_threshold'])
        metric, weight = rhog, glint_weight(rhog, settings)
    return np.where(valid, metric, np.inf), np.where(valid, weight, 0).astype(np.float32)


def matching(table, stem, wave):
    """Clave ya registrada para una variable equivalente (mismo nombre base y onda cercana), o None."""
    for key in table:
        if key[0] == stem and (key[1] == wave or (None not in (key[1], wave)
                                                  and abs(key[1]-wave) <= WAVELENGTH_TOLERANCE)):
            return key
    return None


def variable_table(file_lists):
    """{nombre de salida: [archivo en cada entrada o None]}, uniendo bandas equivalentes entre entradas."""
    table = {}
    for index, files in enumerate(file_lists):
        for file in files:
            name = file.removesuffix('.tif')
            if name in LAYERS:
                continue
            wave = wavelength(name)
            stem = name.rsplit('_', 1)[0] if wave else name
            key = matching(table, stem, wave) or (stem, wave)
            entry = table.setdefault(key, {'name': name, 'files': [None]*len(file_lists)})
            entry['files'][index] = file
    return {entry['name']: entry['files'] for entry in table.values()}


def stack(folders, files, start, count, width):
    """Capas de una variable de cada entrada en un bloque; NaN donde la entrada no la tiene."""
    return np.stack([read_rows(Path(folder)/file, start, count) if file else np.full((count, width), np.nan, np.float32)
                     for folder, file in zip(folders, files)])


def take(values, choice):
    """Elige por píxel la capa indicada por `choice` en una pila (capas, filas, columnas)."""
    return np.take_along_axis(values, choice[None], axis=0)[0]


def best_pixel(metric, dates, counts):
    """Mejor píxel: observación elegida, píxeles con dato y capas de fecha, observaciones y métrica."""
    choice = np.argmin(metric, axis=0)
    seen = np.isfinite(metric).any(axis=0)
    layers = {'fecha_origen': np.where(seen, take(dates, choice), 0),
              'n_observaciones': np.where(np.isfinite(metric), counts, 0).sum(axis=0),
              'metrica': np.where(seen, take(metric, choice), np.nan).astype(np.float32)}
    return lambda values: np.where(seen, take(values, choice), np.nan).astype(np.float32), layers


def weighted_mean(weight, dates, counts):
    """Media ponderada: función que promedia una variable y capas de fecha, observaciones y peso total.

    Cada variable usa solo los pesos de las observaciones donde tiene dato.
    """
    total = weight.sum(axis=0)
    seen = total > 0

    def mean(values):
        usable = np.where(np.isfinite(values), weight, 0)
        weights = usable.sum(axis=0)
        summed = (np.where(usable > 0, values, 0)*usable).sum(axis=0)
        return np.where(weights > 0, summed/np.where(weights > 0, weights, 1), np.nan).astype(np.float32)

    layers = {'fecha_origen': np.where(seen, take(dates, np.argmax(weight, axis=0)), 0),
              'n_observaciones': np.where(weight > 0, counts, 0).sum(axis=0),
              'peso_total': np.where(seen, total, np.nan).astype(np.float32)}
    return mean, layers


def combine(method, family, metric, weight, dates, counts):
    """Reductor de variables y capas propias del método; la métrica del mejor píxel vuelve a sus unidades."""
    if method == WEIGHTED:
        return weighted_mean(weight, dates, counts)
    reduce, layers = best_pixel(metric, dates, counts)
    measure = layers.pop('metrica')
    layers[glint_layer(family)] = -measure if family == 'olci' else measure
    return reduce, layers


def writers(staging, zone_grid, names, method, family, meta):
    """Un LayerWriter por variable y por capa propia del compuesto."""
    measure = glint_layer(family) if method == BEST else 'peso_total'
    result = {name: LayerWriter(Path(staging)/(name+'.tif'), zone_grid, name=name, metadata=meta)
              for name in [*names, measure]}
    result['fecha_origen'] = LayerWriter(Path(staging)/'fecha_origen.tif', zone_grid, gdal.GDT_Int32, 0,
                                         'fecha_origen', {**meta, 'valor': 'AAAAMMDD'})
    result['n_observaciones'] = LayerWriter(Path(staging)/'n_observaciones.tif', zone_grid, gdal.GDT_Int16, 0,
                                            'n_observaciones', meta)
    return result


def daily_observations(storage, members, family, settings, bits, start, count):
    """Una observación por día en un bloque: escena elegida (menor glint), métrica, peso y fecha."""
    metrics, weights = zip(*(scene_glint(storage/m['carpeta'], start, count, family, settings, bits) for m in members))
    metrics, weights = np.stack(metrics), np.stack(weights)
    chosen, metric, weight, dates = [], [], [], []
    for day in sorted({m['fecha'] for m in members}):
        indexes = np.array([i for i, m in enumerate(members) if m['fecha'] == day])
        local = np.argmin(metrics[indexes], axis=0)
        chosen.append(indexes[local])
        metric.append(take(metrics[indexes], local))
        weight.append(take(weights[indexes], local))
        dates.append(np.full(local.shape, int(day.replace('-', '')), np.int32))
    return np.stack(chosen), np.stack(metric), np.stack(weight), np.stack(dates)


def write_monthly(storage, config, zone, members, method, target):
    """Escribe el compuesto mensual de un método en `target` y devuelve su tamaño."""
    family, zone_grid = config['family'], config['zones'][zone]['grid']
    settings, bits = config['superimagen']['glint'], config['superimagen']['composite']['discard_flag_bits']
    folders = [storage/m['carpeta'] for m in members]
    table = variable_table([json.loads(m['variables']) for m in members])
    staging = staging_for(target)
    output = writers(staging, zone_grid, table, method, family, {'zona': zone, 'metodo': method, 'escenas': len(members)})
    width = zone_grid['shape_yx'][1]
    for start, count in row_blocks(zone_grid):
        chosen, metric, weight, dates = daily_observations(storage, members, family, settings, bits, start, count)
        reduce, layers = combine(method, family, metric, weight, dates, np.ones(dates.shape, np.int16))
        for name, files in table.items():
            scenes = stack(folders, files, start, count, width)
            layers[name] = reduce(np.stack([take(scenes, day) for day in chosen]))
        for name, writer in output.items():
            writer.write(start, layers[name])
    size = sum(writer.close() for writer in output.values())
    publish(staging, target)
    return size


def write_aggregate(storage, config, zone, monthlies, method, target):
    """Escribe un compuesto estacional o anual desde los mensuales del mismo método y devuelve su tamaño."""
    family, zone_grid = config['family'], config['zones'][zone]['grid']
    folders = [storage/m['carpeta'] for m in monthlies]
    table = variable_table([sorted(path.name for path in folder.glob('*.tif')) for folder in folders])
    measure = glint_layer(family) if method == BEST else 'peso_total'
    staging = staging_for(target)
    output = writers(staging, zone_grid, table, method, family, {'zona': zone, 'metodo': method, 'meses': len(monthlies)})
    width = zone_grid['shape_yx'][1]
    for start, count in row_blocks(zone_grid):
        layer = lambda name: np.stack([read_rows(folder/(name+'.tif'), start, count) for folder in folders])
        dates = np.nan_to_num(layer('fecha_origen')).astype(np.int32)
        counts = np.nan_to_num(layer('n_observaciones')).astype(np.int16)
        values = layer(measure)
        metric = np.where(np.isfinite(values), -values if family == 'olci' else values, np.inf)
        reduce, layers = combine(method, family, metric, np.nan_to_num(values), dates, counts)
        for name, files in table.items():
            layers[name] = reduce(stack(folders, files, start, count, width))
        for name, writer in output.items():
            writer.write(start, layers[name])
    size = sum(writer.close() for writer in output.values())
    publish(staging, target)
    return size


def month_bounds(month):
    """Inicio incluido y fin excluido ('AAAA-MM-DD HH:MM:SS') de un mes 'AAAA-MM'."""
    year, number = map(int, month.split('-'))
    return f'{month}-01 00:00:00', f'{year+number//12}-{number % 12+1:02d}-01 00:00:00'


def last_day(month):
    """Último día 'AAAA-MM-DD' de un mes 'AAAA-MM'."""
    following = date.fromisoformat(month_bounds(month)[1][:10])
    return (following-timedelta(days=1)).isoformat()


def months_between(start, end):
    """Meses 'AAAA-MM' que tocan el intervalo [start, end) del perfil."""
    year, month = int(start[:4]), int(start[5:7])
    months = []
    while f'{year}-{month:02d}-01' < end[:10]:
        months.append(f'{year}-{month:02d}')
        year, month = year+month//12, month % 12+1
    return months


def month_complete(catalog, config, zone, month, today):
    """Un mes está completo si ya terminó, se buscó entero y todas sus escenas de la zona tienen resultado."""
    first, last = month_bounds(month)
    aoi, family = config['aoi']['id'], config['family']
    return (last[:10] <= today and catalog.searched(aoi, family, first, last)
            and not catalog.unfinished(aoi, family, zone, first, last))


def periods(months):
    """Estaciones y años cuyos meses están todos en `months`: [(tipo, periodo, meses)]."""
    found, present = [], set(months)
    years = sorted({int(m[:4]) for m in months})
    for year in years:
        for season, numbers in SEASONS.items():
            needed = [f'{year-1 if n == 12 else year}-{n:02d}' for n in numbers]
            if set(needed) <= present:
                found.append((SEASONAL, f'{year}-{season}', needed))
        needed = [f'{year}-{n:02d}' for n in range(1, 13)]
        if set(needed) <= present:
            found.append((ANNUAL, str(year), needed))
    return found


def compose(catalog, config, kind, zone, period, method, inputs, members, signature_parts, writer):
    """Escribe y registra un compuesto si su firma cambió; devuelve HECHO o AL_DIA."""
    aoi, sensor = config['aoi']['id'], SENSOR_TAG[config['family']]
    folder = Path('superimagen')/'calidad_agua'/zone/sensor/kind/period/method
    firm = digest({**signature_parts, 'metodo': method, 'version': METHOD_VERSION})
    existing = catalog.composite(kind, method, aoi, zone, sensor, period)
    if existing and existing['firma'] == firm and (catalog.storage/folder).is_dir():
        return 'AL_DIA'
    size = writer(catalog.storage, config, zone, inputs, method, catalog.storage/folder)
    catalog.record_composite(kind, method, aoi, zone, sensor, period, str(folder), firm, size, members,
                             {'entradas': len(inputs)})
    return 'HECHO'


def update(catalog, config, zones, today=None):
    """Compuestos de los meses completos del perfil y de sus estaciones y años; {estado: cantidad}.

    No descarga nada: usa lo que ya está en superimagen/escenas. Un mes sin escenas válidas no
    tiene compuesto, pero cuenta como completo para su estación y su año.
    """
    today = today or datetime.now(timezone.utc).date().isoformat()
    aoi, sensor = config['aoi']['id'], SENSOR_TAG[config['family']]
    settings = {'glint': config['superimagen']['glint'], 'bits': config['superimagen']['composite']['discard_flag_bits']}
    counts = Counter()
    for zone in zones:
        complete = [m for m in months_between(config['start'], config['end'])
                    if month_complete(catalog, config, zone, m, today)]
        for month in complete:
            members = catalog.products(aoi, zone, sensor, month+'-01', last_day(month))
            if not members:
                counts['SIN_ESCENAS'] += 1
                continue
            parts = {'productos': [[m['id'], m['fecha_proceso']] for m in members], **settings}
            for method in METHODS:
                counts[compose(catalog, config, MONTHLY, zone, month, method, members, [m['id'] for m in members],
                               parts, write_monthly)] += 1
        for kind, period, months in periods(complete):
            for method in METHODS:
                monthlies = [c for c in catalog.composites(MONTHLY, aoi, zone, sensor, method) if c['periodo'] in months]
                if not monthlies:
                    continue
                members = sorted({p for c in monthlies for p in catalog.composite_members(c['id'])})
                parts = {'mensuales': [[c['id'], c['firma']] for c in monthlies]}
                counts[compose(catalog, config, kind, zone, period, method, monthlies, members, parts,
                               write_aggregate)] += 1
    return dict(counts)
