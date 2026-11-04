"""Zonas del AOI: geometría del shapefile, grilla propia por sensor y cobertura de huellas.

Cada zona tiene su EPSG (UTM de la zona) y, por sensor, una grilla en su resolución nativa
alineada a múltiplos de esa resolución. Así las escenas de un mismo sensor caen siempre en los
mismos píxeles y el compuesto no remuestrea. Las grillas se calculan de la geometría: no se copian
a mano en el perfil.
"""
import math
import re
import unicodedata
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()
osr.UseExceptions()


def spatial_reference(epsg):
    """Referencia espacial EPSG con orden de ejes x=longitud/este, y=latitud/norte."""
    reference = osr.SpatialReference()
    reference.ImportFromEPSG(int(epsg))
    reference.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return reference


def slug(name):
    """Identificador de carpeta de una zona: 'La Parguera Guanica' → 'la_parguera_guanica'."""
    ascii_name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '_', ascii_name.lower()).strip('_')


def read_zones(path, name_field='Name'):
    """Polígonos del shapefile (ZIP o .shp) en WGS84 (WKT), por nombre de zona."""
    path = str(path)
    source = gdal.OpenEx(('/vsizip/'+path) if path.endswith('.zip') else path, gdal.OF_VECTOR)
    layer = source.GetLayer(0)
    to_wgs84 = osr.CoordinateTransformation(layer.GetSpatialRef(), spatial_reference(4326))
    zones = {}
    for feature in layer:
        geometry = feature.GetGeometryRef().Clone()
        geometry.Transform(to_wgs84)
        zones[feature.GetField(name_field)] = geometry.ExportToWkt()
    return zones


def transformed(wkt, epsg_from, epsg_to):
    """Geometría WKT reproyectada entre dos EPSG."""
    geometry = ogr.CreateGeometryFromWkt(wkt)
    geometry.Transform(osr.CoordinateTransformation(spatial_reference(epsg_from), spatial_reference(epsg_to)))
    return geometry


def grid(wkt, epsg, resolution):
    """Grilla de la zona: rectángulo envolvente en el EPSG de la zona, ampliado a múltiplos de la resolución.

    Devuelve xrange (oeste→este) e yrange (norte→sur) en metros, la forma (filas, columnas) y la
    transformada GDAL. Es la convención de rangos que espera `output_projection` de ACOLITE.
    """
    west, east, south, north = transformed(wkt, 4326, epsg).GetEnvelope()
    x0, x1 = math.floor(west/resolution)*resolution, math.ceil(east/resolution)*resolution
    y0, y1 = math.floor(south/resolution)*resolution, math.ceil(north/resolution)*resolution
    return {'epsg': int(epsg), 'resolution_m': resolution, 'xrange_m': [x0, x1], 'yrange_m': [y1, y0],
            'shape_yx': [round((y1-y0)/resolution), round((x1-x0)/resolution)],
            'geotransform': [x0, resolution, 0, y1, 0, -resolution]}


def axes(zone_grid):
    """Centros de píxel esperados (x, y) de una grilla, como los escribe ACOLITE en el NetCDF."""
    import numpy as np
    resolution = zone_grid['resolution_m']
    (x0, x1), (y1, y0) = zone_grid['xrange_m'], zone_grid['yrange_m']
    return np.arange(x0+resolution/2, x1, resolution), np.arange(y1-resolution/2, y0, -resolution)


def limit(zone_grid):
    """`limit` de ACOLITE (sur, oeste, norte, este en grados) que contiene toda la grilla de la zona.

    Se toma la envolvente geográfica de las cuatro esquinas más un píxel: el rectángulo UTM girado
    no cabe en la envolvente de la zona en grados, y sin ese margen la grilla quedaría sin datos en
    los bordes al proyectar.
    """
    resolution = zone_grid['resolution_m']
    (x0, x1), (y1, y0) = zone_grid['xrange_m'], zone_grid['yrange_m']
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in ((x0-resolution, y0-resolution), (x1+resolution, y0-resolution), (x1+resolution, y1+resolution),
                 (x0-resolution, y1+resolution), (x0-resolution, y0-resolution)):
        ring.AddPoint_2D(x, y)
    rectangle = ogr.Geometry(ogr.wkbPolygon)
    rectangle.AddGeometry(ring)
    west, east, south, north = transformed(rectangle.ExportToWkt(), zone_grid['epsg'], 4326).GetEnvelope()
    return [round(south, 6), round(west, 6), round(north, 6), round(east, 6)]


def coverage(footprint_wkt, zone_wkt):
    """Fracción del área de la zona cubierta por la huella de una escena (0 a 1), en grados."""
    zone = ogr.CreateGeometryFromWkt(zone_wkt)
    footprint = ogr.CreateGeometryFromWkt(footprint_wkt)
    if not footprint.IsValid():
        footprint = footprint.Buffer(0)
    return zone.Intersection(footprint).GetArea()/zone.GetArea() if zone.GetArea() else 0.0


def rasterize(wkt, zone_grid, epsg_of_wkt=4326):
    """Máscara booleana (filas, columnas) de los píxeles de la grilla cuyo centro cae dentro del polígono."""
    import numpy as np
    rows, columns = zone_grid['shape_yx']
    target = gdal.GetDriverByName('MEM').Create('', columns, rows, 1, gdal.GDT_Byte)
    target.SetGeoTransform(zone_grid['geotransform'])
    target.SetProjection(spatial_reference(zone_grid['epsg']).ExportToWkt())
    memory = ogr.GetDriverByName('Memory').CreateDataSource('')
    layer = memory.CreateLayer('zona', spatial_reference(zone_grid['epsg']), ogr.wkbPolygon)
    feature = ogr.Feature(layer.GetLayerDefn())
    feature.SetGeometry(transformed(wkt, epsg_of_wkt, zone_grid['epsg']))
    layer.CreateFeature(feature)
    gdal.RasterizeLayer(target, [1], layer, burn_values=[1])
    return target.GetRasterBand(1).ReadAsArray().astype(bool) if rows and columns else np.zeros((0, 0), bool)
