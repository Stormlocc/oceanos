"""Pruebas de la superimagen: exportación de escenas, máscara de tierra, sargazo, compuestos y flujo por zona.

Datos sintéticos pequeños en una grilla de 4 × 6 píxeles; sin red ni ACOLITE real.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
from oceanos.catalog import Catalog
from oceanos.config import PROFILE, file_hash, profile
from oceanos.escenas import QUALITY_BANDS, read_band, write_cog
from oceanos.native import scene_identity
from oceanos.pipeline import Pipeline, StageError
import sin_red

# Sin red en las pruebas: unittest llama estos hooks del módulo.
setUpModule, tearDownModule = sin_red.setUpModule, sin_red.tearDownModule

GRID = {'epsg': 32619, 'resolution_m': 10, 'xrange_m': [700000, 700060], 'yrange_m': [2000040, 2000000],
        'shape_yx': [4, 6], 'geotransform': [700000, 10, 0, 2000040, 0, -10]}
SHAPE = (4, 6)
ZONE = 'ponce_guayanilla'
SCENE = 'S2B_MSIL1C_20251216T150719_N0511_R082_T19QGV_20251216T182348.SAFE'


def full(value, dtype=np.float32):
    return np.full(SHAPE, value, dtype)


def config_for(start='2025-12-01', end='2026-01-01'):
    """Perfil real con una sola zona cuya grilla es la pequeña de las pruebas."""
    config = profile(PROFILE, 'sentinel2', start=start, end=end, zones=[ZONE])
    config['zones'][ZONE] = {**config['zones'][ZONE], 'grid': GRID}
    return config


def scene_folder(folder, variables, rhog, flags=None, swir=0.0, angle=40.0):
    """Carpeta de escena como la deja la exportación: un COG por variable y calidad.tif."""
    folder.mkdir(parents=True, exist_ok=True)
    for name, values in variables.items():
        write_cog(folder/(name+'.tif'), [full(values) if np.isscalar(values) else values.astype(np.float32)], GRID)
    bits = [full(0.0) for _ in range(6)]
    for bit, mask in (flags or {}).items():
        bits[bit] = mask.astype(np.float32)
    quality = bits + [full(rhog) if np.isscalar(rhog) else rhog.astype(np.float32), full(swir), full(np.nan), full(angle)]
    write_cog(folder/'calidad.tif', quality, GRID, names=QUALITY_BANDS)
    return sorted(p.name for p in folder.iterdir())


class StorageCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cat = Catalog(self.temp.name)
        self.storage = self.cat.storage

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def product(self, name, date, variables, rhog, sensor='S2', **quality):
        """Registra un producto de escena OK con su carpeta en superimagen/escenas."""
        relative = Path('superimagen')/'escenas'/ZONE/sensor/f'{date}_{name}'
        files = scene_folder(self.storage/relative, variables, rhog, **quality)
        scene = self.cat.upsert_scene({'provider': 'LOCAL', 'product': f'{name}_{date}', 'format': 'SAFE',
                                       'identity': scene_identity(SCENE)})
        return self.cat.record_product(scene, ZONE, 'water2coast_v1', estado='OK', sensor=sensor, fecha=date,
                                       carpeta=str(relative), variables=files, instante_utc=date+' 15:07')


class ExportTests(unittest.TestCase):
    def setUp(self):
        import netCDF4
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        x = np.arange(700005, 700060, 10); y = np.arange(2000035, 2000000, -10)
        self.l2r, self.l2w = root/'l2r.nc', root/'l2w.nc'
        for path, names in ((self.l2r, ['rhog_ref', 'rhos_1614']), (self.l2w, ['Rrs_443', 'Rrs_1614', 'Rrs_2202', 'fai'])):
            with netCDF4.Dataset(path, 'w') as ds:
                ds.createDimension('x', 6); ds.createDimension('y', 4)
                ds.createVariable('x', 'f8', ('x',))[:] = x; ds.createVariable('y', 'f8', ('y',))[:] = y
                for index, name in enumerate(names):
                    ds.createVariable(name, 'f4', ('y', 'x'))[:] = full(0.001*(index+1))
                ds.sza, ds.vza, ds.raa = 30.0, 5.0, 100.0
                if path == self.l2w:
                    flags = np.zeros(SHAPE, np.int32); flags[0, :] = 0b10  # cirrus en la fila superior
                    ds.createVariable('l2_flags', 'i4', ('y', 'x'))[:] = flags
        mask = np.zeros(SHAPE, np.uint8); mask[:, 0] = 1; mask[:, 5] = 2  # tierra y fuera de la zona
        self.mask = root/'mask.tif'
        write_cog(self.mask, [mask], GRID, nodata=None)
        self.ac = Mock(); self.ac.shared.glint_angle.side_effect = lambda sza, vza, raa: np.full(sza.shape, 25.0)

    def tearDown(self):
        self.temp.cleanup()

    def test_export_writes_cogs_with_quality_and_land_as_nodata(self):
        from oceanos.escenas import export, verify
        target = Path(self.temp.name)/'escenas'/'2025-12-16_19QGV'
        result = export(self.ac, self.l2r, self.l2w, self.mask, target, GRID, {'zona': ZONE})
        self.assertEqual(sorted(result['files']), ['Rrs_1614.tif', 'Rrs_2202.tif', 'Rrs_443.tif', 'calidad.tif', 'fai.tif'])
        self.assertTrue(verify(target, result['files']))
        self.assertFalse(target.with_name(target.name+'.parcial').exists())
        fai = read_band(target/'fai.tif')
        self.assertTrue(np.isnan(fai[:, 0]).all() and np.isnan(fai[:, 5]).all())
        self.assertTrue(np.allclose(fai[:, 1:5], 0.004))
        quality = {name: read_band(target/'calidad.tif', index) for index, name in enumerate(QUALITY_BANDS, 1)}
        self.assertTrue((quality['flag_cirrus'][0, 1:5] == 1).all() and (quality['flag_cirrus'][1:, 1:5] == 0).all())
        self.assertTrue(np.allclose(quality['rhog_ref'][:, 1:5], 0.001))
        self.assertTrue(np.allclose(quality['residuo_rrs_swir1'][:, 1:5], 0.002))
        self.assertTrue(np.allclose(quality['residuo_rrs_swir2'][:, 1:5], 0.003))
        self.assertEqual((result['angulo_glint_deg'], result['nubes_flags_pct'], result['agua_vista_pct']), (25.0, 25.0, 100.0))
        self.assertEqual(read_band(target/'fai.tif').shape, SHAPE)

    def test_verify_rejects_missing_or_truncated_cog(self):
        from oceanos.escenas import export, verify
        target = Path(self.temp.name)/'escena'
        files = export(self.ac, self.l2r, self.l2w, self.mask, target, GRID, {})['files']
        (target/'fai.tif').write_bytes(b'x')
        with self.assertRaises(ValueError): verify(target, files)


class CloudTests(unittest.TestCase):
    """Nubes sobre la zona con la máscara del propio L1 (S2 MSK_CLASSI_B00, Landsat QA_PIXEL)."""
    def setUp(self):
        from oceanos.zonas import transformed
        self.temp = tempfile.TemporaryDirectory()
        square = 'POLYGON ((700000 2000000, 700600 2000000, 700600 2000600, 700000 2000600, 700000 2000000))'
        self.zone = {'wkt': transformed(square, 32619, 4326).ExportToWkt(), 'epsg': 32619}
        self.grid = {'epsg': 32619, 'resolution_m': 60, 'xrange_m': [699400, 701200], 'yrange_m': [2001200, 1999400],
                     'shape_yx': [30, 30], 'geotransform': [699400, 60, 0, 2001200, 0, -60]}

    def tearDown(self):
        self.temp.cleanup()

    def raster(self, path, bands, data_type=None):
        from osgeo import gdal
        path.parent.mkdir(parents=True, exist_ok=True)
        write_cog(path, bands, {**self.grid, 'resolution_m': 60}, data_type=data_type or gdal.GDT_Byte, nodata=None)

    def test_sentinel2_classification_mask(self):
        from oceanos.escenas import cloud_fraction
        safe = Path(self.temp.name)/'S2.SAFE'
        opaque = np.zeros((30, 30), np.uint8); opaque[:, :15] = 1
        # GDAL reconoce el formato por el contenido: un GeoTIFF con nombre .jp2 sirve de L1C sintético.
        self.raster(safe/'GRANULE/L1C_T19QGV/QI_DATA/MSK_CLASSI_B00.jp2', [opaque, np.zeros((30, 30), np.uint8)])
        self.raster(safe/'GRANULE/L1C_T19QGV/IMG_DATA/T19QGV_B01.jp2', [np.ones((30, 30), np.uint8)])
        result = cloud_fraction(safe, 'sentinel2', self.zone)
        self.assertEqual((result['cobertura_pct'], result['origen']), (100.0, 'MSK_CLASSI_B00'))
        self.assertAlmostEqual(result['nubes_pct'], 50.0, delta=12)

    def test_landsat_qa_pixel_and_partial_coverage(self):
        from osgeo import gdal
        from oceanos.escenas import cloud_fraction
        folder = Path(self.temp.name)/'LC09'
        qa = np.full((30, 30), 0, np.uint16); qa[:15, :] = 1; qa[15:, :5] = 0b1000  # relleno arriba, nube abajo
        self.raster(folder/'LC09_L1TP_005048_QA_PIXEL.TIF', [qa], gdal.GDT_UInt16)
        result = cloud_fraction(folder, 'landsat', self.zone)
        self.assertEqual(result['origen'], 'QA_PIXEL')
        self.assertTrue(0 < result['cobertura_pct'] < 100)
        self.assertIsNone(cloud_fraction(Path(self.temp.name)/'nada', 'olci', self.zone))


class MaskTests(unittest.TestCase):
    def test_land_mask_from_worldcover_with_margin_and_outside(self):
        from oceanos.mascara import LAND, OUTSIDE, WATER, build
        from osgeo import gdal
        with tempfile.TemporaryDirectory() as tmp:
            classes = np.full((8, 12), 80, np.uint8); classes[:, :2] = 10; classes[:, 2:4] = 95  # tierra y manglar
            tile = Path(tmp)/'tile.tif'
            grid10 = {**GRID, 'shape_yx': [8, 12], 'resolution_m': 5, 'geotransform': [700000, 5, 0, 2000040, 0, -5]}
            write_cog(tile, [classes], grid10, data_type=gdal.GDT_Byte, nodata=None)
            zone = {'wkt': 'POLYGON ((-67 17, -60 17, -60 19, -67 19, -67 17))'}
            settings = {'water_classes': [80, 0], 'margin_pixels': 1}
            with patch('oceanos.mascara.rasterize', return_value=np.ones(SHAPE, bool)):
                mask = build([tile], zone, GRID, settings)
        # Columnas 0-1 (tierra y manglar) más un píxel de margen hacia el mar.
        self.assertTrue((mask[:, :3] == LAND).all() and (mask[:, 3:] == WATER).all())
        self.assertNotIn(OUTSIDE, mask)

    def test_worldcover_download_retries_then_explains(self):
        from oceanos.mascara import download
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def flaky(url, target):
                calls.append(url)
                if len(calls) < 2:
                    raise TimeoutError()
                Path(target).write_bytes(b'tif')
            paths = download(Path(tmp), {'a.tif': 'https://x/a.tif'}, flaky, wait=lambda _: None)
            self.assertEqual((len(calls), [p.name for p in paths]), (2, ['a.tif']))
            with self.assertRaises(ValueError) as caught:
                download(Path(tmp), {'b.tif': 'https://x/b.tif'}, Mock(side_effect=TimeoutError()), wait=lambda _: None)
            self.assertIn('b.tif', str(caught.exception))


class SargassumTests(StorageCase):
    def test_daily_max_fai_with_ndvi_and_origin_from_same_scene(self):
        from oceanos import sargazo
        config = config_for()
        cirrus = np.zeros(SHAPE, bool); cirrus[0, 0] = True
        first = self.product('19QGV', '2025-12-16', {'fai': full(0.02), 'ndvi': full(0.1)}, 0.001, flags={1: cirrus})
        fai = full(0.01); fai[:, 3:] = 0.05
        second = self.product('19QFV', '2025-12-16', {'fai': fai, 'ndvi': full(0.3)}, 0.001)
        self.assertEqual(sargazo.update(self.cat, config, [ZONE], '2025-12-01', '2025-12-31'), {'HECHO': 1})
        folder = self.storage/'superimagen/sargazo'/ZONE/'S2/diario/2025-12-16'
        best, ndvi, origin = (read_band(folder/f'{n}.tif') for n in ('fai', 'ndvi', 'escena_origen'))
        self.assertEqual((origin[1, 0], origin[1, 4], origin[0, 0]), (first, second, second))
        self.assertAlmostEqual(float(best[0, 0]), 0.01, 6)   # la escena con cirros no cuenta
        self.assertAlmostEqual(float(ndvi[1, 4]), 0.3, 6)
        row = self.cat.composite('sargazo_diario', 'maximo_fai', 'water2coast_v1', ZONE, 'S2', '2025-12-16')
        self.assertEqual(sorted(self.cat.composite_members(row['id'])), sorted([first, second]))
        self.assertEqual(sargazo.update(self.cat, config, [ZONE], '2025-12-01', '2025-12-31'), {'AL_DIA': 1})


class CompositeTests(StorageCase):
    def searched(self, config):
        search = self.cat.search_start('CDSE', config, 1)
        self.cat.search_finish(search, 'OK', {'count': 0})

    def test_glint_weight(self):
        from oceanos.componer import glint_weight
        weights = glint_weight(np.array([0.0, 0.005, 0.0125, 0.02, 0.03, np.nan]), {'full_weight_max': 0.005, 'discard_above': 0.02})
        self.assertTrue(np.allclose(weights, [1, 1, 0.5, 0, 0, 0]))

    def test_twin_satellite_bands_share_one_output(self):
        from oceanos.componer import variable_table
        table = variable_table([['Rrs_665.tif', 'chl_oc3.tif', 'calidad.tif'], ['Rrs_664.tif', 'Rrs_704.tif']])
        self.assertEqual(table, {'Rrs_665': ['Rrs_665.tif', 'Rrs_664.tif'], 'chl_oc3': ['chl_oc3.tif', None],
                                 'Rrs_704': [None, 'Rrs_704.tif']})

    def test_monthly_methods_and_season_from_monthlies(self):
        from oceanos import componer
        config = config_for('2025-12-01', '2026-03-01')
        cirrus = np.zeros(SHAPE, bool); cirrus[0, 1] = True
        high = full(0.001); high[0, 2] = 0.03; high[0, 3] = np.nan
        self.product('19QGV', '2025-12-16', {'Rrs_665': full(1.0), 'chl_oc3': full(10.0)}, high, flags={1: cirrus})
        self.product('19QFV', '2025-12-16', {'Rrs_665': full(2.0), 'chl_oc3': full(20.0)}, 0.003)
        later = full(0.0125); later[0, 2] = 0.03; later[0, 3] = np.nan
        self.product('19QGV', '2025-12-26', {'Rrs_664': full(4.0)}, later)
        for config_part in (config,):
            self.searched(config_part)
        made = componer.update(self.cat, config, [ZONE], today='2026-03-05')
        self.assertEqual(made, {'HECHO': 4, 'SIN_ESCENAS': 2})
        base = self.storage/'superimagen/calidad_agua'/ZONE/'S2'
        best, mean = base/'mensual/2025-12/mejor_pixel', base/'mensual/2025-12/media_ponderada'
        self.assertEqual(sorted(p.name for p in best.iterdir()),
                         ['Rrs_665.tif', 'chl_oc3.tif', 'fecha_origen.tif', 'n_observaciones.tif', 'rhog_ref.tif'])
        a, b = read_band(best/'Rrs_665.tif'), read_band(mean/'Rrs_665.tif')
        # (a) menor glint: la escena de rhog 0,001; donde tiene cirros gana la otra del mismo día.
        self.assertEqual((a[1, 1], a[0, 1]), (1.0, 2.0))
        self.assertEqual(read_band(best/'fecha_origen.tif')[1, 1], 20251216)
        self.assertEqual(read_band(best/'n_observaciones.tif')[1, 1], 2)
        # (b) un valor por día (el de menor glint) y peso por glint: (1·1 + 4·0,5)/1,5 = 2.
        self.assertAlmostEqual(float(b[1, 1]), 2.0, 5)
        self.assertAlmostEqual(float(read_band(mean/'peso_total.tif')[1, 1]), 1.5, 5)
        # rhog_ref 0,03 en un día: (b) lo descarta y queda el otro día con su peso.
        self.assertAlmostEqual(float(b[0, 2]), 2.0, 5)
        # Sin rhog_ref (ACOLITE no corrigió) en ninguna observación del día 16 de una escena: queda la otra.
        self.assertAlmostEqual(float(a[0, 3]), 2.0, 5)
        # Una variable que falta en una escena solo pondera donde existe.
        self.assertAlmostEqual(float(read_band(mean/'chl_oc3.tif')[1, 1]), 10.0, 5)
        season = base/'estacional/2026-DEF/media_ponderada/Rrs_665.tif'
        self.assertAlmostEqual(float(read_band(season)[1, 1]), 2.0, 5)
        row = self.cat.composite('estacional', 'mejor_pixel', 'water2coast_v1', ZONE, 'S2', '2026-DEF')
        self.assertEqual(len(self.cat.composite_members(row['id'])), 3)
        self.assertEqual(componer.update(self.cat, config, [ZONE], today='2026-03-05'), {'AL_DIA': 4, 'SIN_ESCENAS': 2})

    def test_month_is_complete_only_when_searched_finished_and_processed(self):
        from oceanos.componer import month_complete
        config = config_for()
        self.assertFalse(month_complete(self.cat, config, ZONE, '2025-12', '2026-01-05'))
        self.searched(config)
        self.assertTrue(month_complete(self.cat, config, ZONE, '2025-12', '2026-01-05'))
        self.assertFalse(month_complete(self.cat, config, ZONE, '2025-12', '2025-12-20'))
        scene = self.cat.upsert_scene({'provider': 'CDSE', 'product': SCENE, 'format': 'SAFE', 'identity': scene_identity(SCENE)})
        self.cat.set_zones(scene, [ZONE])
        self.assertFalse(month_complete(self.cat, config, ZONE, '2025-12', '2026-01-05'))
        self.cat.record_product(scene, ZONE, 'water2coast_v1', estado='NUBOSA', sensor='S2', fecha='2025-12-16')
        self.assertTrue(month_complete(self.cat, config, ZONE, '2025-12', '2026-01-05'))

    def test_periods_need_every_month(self):
        from oceanos.componer import periods
        self.assertEqual(periods(['2025-12', '2026-01']), [])
        self.assertEqual(periods(['2025-12', '2026-01', '2026-02']), [('estacional', '2026-DEF', ['2025-12', '2026-01', '2026-02'])])


class ZoneFlowTests(StorageCase):
    """Pipeline.run con las etapas aisladas simuladas: una descarga, varias zonas y linaje."""
    def setUp(self):
        super().setUp()
        self.config = profile(PROFILE, 'sentinel2', start='2025-12-01', end='2026-01-01',
                              zones=['la_parguera_guanica', 'ponce_guayanilla'])
        self.source = {'provider': 'CDSE', 'product': SCENE, 'format': 'SAFE', 'id': 'cdse-id',
                       'identity': scene_identity(SCENE), 'metadata': {'Checksum': [{'Algorithm': 'MD5', 'Value': 'm'}]}}
        self.scene = self.cat.upsert_scene(self.source)
        self.calls, self.clouds, self.defaults = [], {'la_parguera_guanica': 80.0, 'ponce_guayanilla': 10.0}, False
        for zone in self.config['zones']:
            from oceanos.mascara import path_for
            path = path_for(self.storage, zone, 'sentinel2', 10); path.parent.mkdir(parents=True, exist_ok=True); path.touch()

    def runner(self):
        runner = object.__new__(Pipeline)
        runner.catalog, runner.config, runner.engine = self.cat, self.config, {'revision': 'test'}
        runner.roots, runner.wait, runner.metrics, runner.progress, runner.resources = [], lambda _: None, [], None, None
        runner.found = runner.current_run = None
        runner.call = self.fake
        return runner

    def fake(self, operation, **args):
        self.calls.append(operation)
        if operation == 'acquire':
            archive = Path(args['raw'])/(SCENE.split('.')[0]+'.zip'); archive.parent.mkdir(parents=True, exist_ok=True)
            archive.write_bytes(b'zip')
            return {'archive': str(archive), 'source': {**args['source'], 'sha256': file_hash(archive)}}
        if operation == 'extract':
            return {'input': str(Path(args['raw'])/SCENE)}
        if operation == 'clouds':
            zone = next(n for n, z in self.config['zones'].items() if z['grid'] == args['zone']['grid'])
            return {'cobertura_pct': 100.0, 'nubes_pct': self.clouds[zone], 'origen': 'MSK_CLASSI_B00'}
        if operation == 'process':
            output = Path(args['output']); output.mkdir(parents=True)
            if getattr(self, 'empty', None) and self.empty in args['settings']:
                (output/'l1r.nc').write_bytes(b'nc')
                return {'files': {'l1r': str(output/'l1r.nc'), 'empty': True}, 'science_metadata': {}}
            files = {level: str(output/f'{level}.nc') for level in ('l1r', 'l2r', 'l2w')}
            for path in files.values(): Path(path).write_bytes(b'nc')
            values = {'uoz': 0.3, 'uwv': 1.5, 'pressure': 1013.25} if self.defaults else {'uoz': 0.27, 'uwv': 3.1, 'pressure': 1012.0}
            return {'files': files, 'science_metadata': values,
                    'ancillary_defaults': {'uoz': 0.3, 'uwv': 1.5, 'pressure': 1013.25}}
        if operation == 'export':
            target = Path(args['target']); target.mkdir(parents=True); (target/'fai.tif').write_bytes(b'tif')
            return {'files': {'fai.tif': 3}, 'variables': ['fai'], 'bytes': 3, 'angulo_glint_deg': 30.0,
                    'nubes_flags_pct': 5.0, 'agua_vista_pct': 99.0}
        raise AssertionError(operation)

    def run_scene(self, runner):
        with patch('oceanos.pipeline.validate'), patch('oceanos.pipeline.verify'), patch('builtins.print'):
            return runner.run(self.scene)

    def test_one_download_processes_each_zone_and_cleans_intermediates(self):
        process = self.run_scene(self.runner())
        self.assertEqual(self.calls, ['acquire', 'extract', 'clouds', 'clouds', 'process', 'export'])
        rows = {r['zona']: r for r in self.cat.db.execute('SELECT * FROM productos_escena')}
        self.assertEqual({z: r['estado'] for z, r in rows.items()}, {'la_parguera_guanica': 'NUBOSA', 'ponce_guayanilla': 'OK'})
        ok = rows['ponce_guayanilla']
        self.assertEqual(ok['carpeta'], 'superimagen/escenas/ponce_guayanilla/S2/2025-12-16_19QGV')
        self.assertEqual((ok['baseline'], ok['via_descarga'], ok['angulo_glint_deg'], json.loads(ok['auxiliares'])['uoz']),
                         ('N0511', 'CDSE', 30.0, 0.27))
        self.assertTrue(ok['sha256'] and json.loads(ok['settings'])['region_name'] == 'ponce_guayanilla')
        self.assertFalse((self.storage/'temporary'/str(process)).exists())
        self.assertEqual(self.cat.process(process)['limpieza'], 'HECHA')
        # Ya terminadas sus zonas, la adquisición no se vuelve a descargar.
        self.calls.clear()
        self.assertIsNone(self.run_scene(self.runner()))
        self.assertEqual(self.calls, [])

    def test_default_ancillary_fails_and_retry_reuses_download(self):
        self.clouds['la_parguera_guanica'] = 10.0
        self.defaults = True
        with self.assertRaises(StageError) as caught:
            self.run_scene(self.runner())
        self.assertEqual(caught.exception.reason, 'AUXILIAR_POR_DEFECTO')
        failed = self.cat.db.execute('SELECT * FROM procesos').fetchone()
        self.assertEqual((failed['estado'], failed['limpieza']), ('FALLIDO', 'APLAZADA'))
        self.assertEqual(self.cat.db.execute("SELECT count(*) FROM productos_escena WHERE estado='OK'").fetchone()[0], 0)
        self.defaults, self.calls = False, []
        self.run_scene(self.runner())
        self.assertNotIn('acquire', self.calls)
        self.assertEqual(self.cat.process(failed['id'])['limpieza'], 'HECHA')
        self.assertEqual(self.cat.db.execute("SELECT count(*) FROM productos_escena WHERE estado='OK'").fetchone()[0], 2)

    def test_zone_outside_the_real_swath_is_sin_datos_not_a_failure(self):
        # La huella toca la zona pero ACOLITE no tiene datos en ella (L1R vacío, sin L2R ni L2W).
        self.clouds['la_parguera_guanica'] = 10.0
        self.empty = 'la_parguera_guanica'
        process = self.run_scene(self.runner())
        rows = {r['zona']: r['estado'] for r in self.cat.db.execute('SELECT * FROM productos_escena')}
        self.assertEqual(rows, {'la_parguera_guanica': 'SIN_DATOS', 'ponce_guayanilla': 'OK'})
        self.assertEqual((self.cat.process(process)['estado'], self.cat.process(process)['limpieza']), ('OK', 'HECHA'))

    def test_native_process_reports_an_empty_zone(self):
        import netCDF4, numpy as np
        from unittest.mock import Mock
        from oceanos.native import process
        output = self.storage/'acolite'; output.mkdir()
        l1r = output/'X_L1R_projected.nc'
        with netCDF4.Dataset(l1r, 'w') as ds:
            ds.createDimension('y', 2); ds.createDimension('x', 3)
            ds.createVariable('rhot_510', 'f4', ('y', 'x'))[:] = np.full((2, 3), np.nan)
        ac = Mock(); ac.acolite.acolite_run.return_value = {'X': {'l1r': [str(l1r)], 'l2r': [], 'l2w': []}}
        self.assertEqual(process(ac, 'in', 'settings.txt', output), {'l1r': str(l1r), 'empty': True})
        # Con datos en el L1R, la falta de L2R sí es un error.
        with netCDF4.Dataset(l1r, 'a') as ds:
            ds['rhot_510'][0, 0] = 0.1
        with self.assertRaises(ValueError):
            process(ac, 'in', 'settings.txt', output)

    def test_missing_land_mask_stops_before_acolite(self):
        from oceanos.mascara import path_for
        path_for(self.storage, 'ponce_guayanilla', 'sentinel2', 10).unlink()
        with self.assertRaises(StageError) as caught:
            self.run_scene(self.runner())
        self.assertEqual(caught.exception.reason, 'SIN_MASCARA')
        self.assertNotIn('process', self.calls)


if __name__ == '__main__':
    unittest.main()
