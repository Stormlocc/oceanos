"""Lectura y escritura por bloques de filas de COG en la grilla de una zona.

Sargazo y compuestos combinan decenas de escenas: leer cada capa entera multiplicaría la RAM por
el número de escenas. Por bloques, la memoria depende solo del ancho de la zona y de cuántas
escenas entran en el periodo.
"""
from pathlib import Path
import numpy as np
from osgeo import gdal
from .escenas import COG_OPTIONS, QUALITY_BANDS
from .zonas import spatial_reference

gdal.UseExceptions()

BLOCK_ROWS = 512


def row_blocks(zone_grid, size=BLOCK_ROWS):
    """Pares (fila inicial, filas) que recorren la grilla de arriba abajo."""
    rows = zone_grid['shape_yx'][0]
    return [(start, min(size, rows-start)) for start in range(0, rows, size)]


def read_rows(path, start, count, band=1):
    """Filas [start, start+count) de una banda como Float32 (NoData como NaN)."""
    dataset = gdal.Open(str(path))
    raster = dataset.GetRasterBand(band)
    values = raster.ReadAsArray(0, start, dataset.RasterXSize, count).astype(np.float32)
    nodata = raster.GetNoDataValue()
    if nodata is not None and not np.isnan(nodata):
        values[values == nodata] = np.nan
    return values


def quality_rows(folder, start, count, name):
    """Filas de una banda de calidad.tif por su nombre (p. ej. 'rhog_ref')."""
    return read_rows(Path(folder)/'calidad.tif', start, count, QUALITY_BANDS.index(name)+1)


class LayerWriter:
    """Escribe una capa por bloques en un GTiff de trabajo y al cerrar la convierte en COG.

    El COG necesita conocer todo el ráster para ordenar sus teselas; por eso se escribe primero un
    GTiff con teselas y después se traduce. El archivo de trabajo se borra al terminar.
    """
    def __init__(self, path, zone_grid, data_type=gdal.GDT_Float32, nodata=float('nan'), name=None, metadata=None):
        self.path = Path(path)
        self.work = self.path.with_suffix('.trabajo.tif')
        rows, columns = zone_grid['shape_yx']
        self.dataset = gdal.GetDriverByName('GTiff').Create(str(self.work), columns, rows, 1, data_type,
                                                            ['TILED=YES', 'COMPRESS=ZSTD', 'BIGTIFF=IF_SAFER'])
        self.dataset.SetGeoTransform(zone_grid['geotransform'])
        self.dataset.SetProjection(spatial_reference(zone_grid['epsg']).ExportToWkt())
        self.band = self.dataset.GetRasterBand(1)
        if nodata is not None:
            self.band.SetNoDataValue(nodata)
        if name:
            self.band.SetDescription(name)
        if metadata:
            self.dataset.SetMetadata({key: str(value) for key, value in metadata.items()})

    def write(self, start, values):
        """Escribe un bloque de filas desde la fila `start`."""
        self.band.WriteArray(values, 0, start)

    def close(self):
        """Convierte el GTiff de trabajo en COG, lo borra y devuelve el tamaño del COG."""
        self.dataset.FlushCache()
        self.band = None
        self.dataset = None
        gdal.Translate(str(self.path), str(self.work), format='COG', creationOptions=COG_OPTIONS)
        self.work.unlink()
        return self.path.stat().st_size
