"""Pruebas de `oceanos sync`: traer la superimagen de otra computadora pegada en superimagen/sincronizar.

Dos storages simulan las dos computadoras; los COG son reales pero de 4 × 6 píxeles. Sin red.
"""
import contextlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from oceanos.catalog import Catalog
from oceanos.escenas import read_band, write_cog
from oceanos.native import acquisition_day, scene_identity
from oceanos.sync import folder, sync
import sin_red

setUpModule, tearDownModule = sin_red.setUpModule, sin_red.tearDownModule

AOI = 'water2coast_v1'
ZONE = 'ponce_guayanilla'
GRID = {'epsg': 32619, 'resolution_m': 10, 'xrange_m': [700000, 700060], 'yrange_m': [2000040, 2000000],
        'shape_yx': [4, 6], 'geotransform': [700000, 10, 0, 2000040, 0, -10]}
SCENE = 'S2B_MSIL1C_20251216T150719_N0511_R082_T19QGV_20251216T182348.SAFE'
# Otra versión del proveedor de la misma adquisición (reproceso con otro baseline).
REPROCESSED = 'S2B_MSIL1C_20251216T150719_N0600_R082_T19QGV_20260301T101010.SAFE'
CLOUDY = 'S2B_MSIL1C_20251221T150719_N0511_R082_T19QGV_20251221T182348.SAFE'
FAILED = 'S2B_MSIL1C_20251226T150719_N0511_R082_T19QGV_20251226T182348.SAFE'
CONFIG = {'aoi': {'id': AOI}}


def scene(cat, name, state=None):
    name = cat.upsert_scene({'provider': 'CDSE', 'product': name, 'format': 'SAFE', 'identity': scene_identity(name)})
    cat.set_zones(name, [ZONE])
    if state:
        cat.scene_state(name, state)
    return name


def product(cat, name, state='OK', when='2026-01-01 10:00:00', value=0.1):
    """Producto por zona como lo deja `run`: proceso, carpeta con COG y fila con su linaje."""
    process = cat.start(name, 'DESCARGA', CONFIG)
    cat.finish(process, 'OK', 'TECNICA_OK', metrics=[{'stage': 'process', 'seconds': 5, 'rss_bytes': 9, 'ok': True}])
    lineage = {'estado': state, 'sensor': 'S2', 'satelite': 'S2B', 'fecha': name[11:15]+'-'+name[15:17]+'-'+name[17:19],
               'proceso': process, 'correccion': {'aot_550_escena': 0.12}}
    if state == 'OK':
        carpeta = f"superimagen/escenas/{ZONE}/S2/{lineage['fecha']}_19QGV"
        target = cat.storage/carpeta
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True)
        for file in ('chl_oc3.tif', 'calidad.tif'):
            write_cog(target/file, [np.full((4, 6), value, np.float32)], GRID)
        files = sorted(p.name for p in target.iterdir())
        lineage.update(carpeta=carpeta, variables=files, bytes=sum((target/f).stat().st_size for f in files))
    row = cat.record_product(name, ZONE, AOI, **lineage)
    with cat.db:
        cat.db.execute('UPDATE productos_escena SET fecha_proceso=? WHERE id=?', (when, row))
    return row


def paste(other, cat):
    """Lo que hace el usuario: copiar escenas/ y catalog.sqlite de la otra computadora a sincronizar/."""
    root = folder(cat.storage)
    root.mkdir(parents=True, exist_ok=True)
    escenas = other.storage/'superimagen'/'escenas'
    if escenas.exists():
        shutil.copytree(escenas, root/'escenas', dirs_exist_ok=True)
    with contextlib.closing(sqlite3.connect(root/'catalog.sqlite')) as copy:
        other.db.backup(copy)
    return root


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.other = Catalog(Path(self.temp.name)/'pc_remota'/'storage')
        self.cat = Catalog(Path(self.temp.name)/'laptop'/'storage')

    def tearDown(self):
        self.other.db.close()
        self.cat.db.close()
        self.temp.cleanup()

    def count(self, sql, *args):
        return self.cat.db.execute(sql, args).fetchone()[0]

    def test_imports_products_searches_and_scenes_then_cleans_up(self):
        ok = product(self.other, scene(self.other, SCENE, 'PROCESADA'))
        product(self.other, scene(self.other, CLOUDY, 'PROCESADA'), state='NUBOSA')
        scene(self.other, FAILED, 'FALLIDA')
        with self.other.db:
            self.other.db.execute("INSERT INTO busquedas(fecha,proveedor,sensor,desde,hasta,estado,aoi) VALUES"
                                  "('2026-01-02 00:00:00','CDSE','sentinel2','2025-12-01 00:00:00','2026-01-01 00:00:00',"
                                  "'OK',?)", (AOI,))
        origin = self.other.db.execute('SELECT proceso FROM productos_escena WHERE id=?', (ok,)).fetchone()[0]
        root = paste(self.other, self.cat)
        report = sync(self.cat, AOI)
        self.assertEqual((len(report['importados']), report['errores'], report['busquedas'], report['escenas']), (2, [], 1, 3))
        self.assertEqual(report['sensores'], {'S2'})
        # Pegado consumido: el catálogo se borró y la carpeta quedó vacía y eliminada.
        self.assertTrue(report['catalogo_borrado'])
        self.assertEqual(report['restos'], [])
        self.assertFalse(root.exists())
        row = self.cat.db.execute("SELECT * FROM productos_escena WHERE estado='OK'").fetchone()
        self.assertEqual(json.loads(row['correccion']), {'aot_550_escena': 0.12})
        self.assertEqual(row['fecha_proceso'], '2026-01-01 10:00:00')
        target = self.cat.storage/row['carpeta']
        self.assertAlmostEqual(float(read_band(target/'chl_oc3.tif')[0, 0]), 0.1, places=6)
        process = self.cat.process(row['proceso'])
        self.assertEqual((process['tipo'], process['limpieza']), ('SINCRONIZADO', 'NO_APLICA'))
        detail = json.loads(process['detalle'])
        self.assertEqual(detail['sincronizado']['proceso_origen'], origin)
        self.assertEqual(detail['metrics'][0]['stage'], 'process')
        # La adquisición traída cuenta como "ya lo tenemos"; la fallida allá entra como NUEVA, fuera de la cola.
        self.assertIn(acquisition_day(scene_identity(SCENE)), self.cat.completed(AOI))
        self.assertEqual(tuple(self.cat.db.execute('SELECT estado, registrada FROM escenas WHERE escena=?', (FAILED,)).fetchone()),
                         ('NUEVA', None))
        self.assertEqual(self.count("SELECT count(*) FROM eventos WHERE tipo='SINCRONIZACION'"), 1)
        # Repetir con lo mismo pegado no duplica nada.
        paste(self.other, self.cat)
        again = sync(self.cat, AOI)
        self.assertEqual((again['importados'], len(again['omitidos']), again['busquedas'], again['escenas']), ([], 2, 0, 0))
        self.assertEqual(self.count('SELECT count(*) FROM productos_escena'), 2)
        self.assertTrue(again['catalogo_borrado'] and not folder(self.cat.storage).exists())

    def test_newest_product_of_the_acquisition_wins(self):
        old = product(self.cat, scene(self.cat, SCENE, 'PROCESADA'), when='2026-01-01 10:00:00', value=0.1)
        composite = self.cat.record_composite('mensual', 'mejor_pixel', AOI, ZONE, 'S2', '2025-12', 'x', 'firma', 1,
                                              [old], {})
        product(self.other, scene(self.other, REPROCESSED, 'PROCESADA'), when='2026-03-02 10:00:00', value=0.2)
        paste(self.other, self.cat)
        report = sync(self.cat, AOI)
        self.assertEqual((report['importados'], len(report['reemplazados'])), ([], 1))
        rows = self.cat.db.execute('SELECT escena, carpeta FROM productos_escena').fetchall()
        self.assertEqual([r['escena'] for r in rows], [REPROCESSED])
        self.assertEqual(self.cat.composite_members(composite), [])
        self.assertAlmostEqual(float(read_band(self.cat.storage/rows[0]['carpeta']/'chl_oc3.tif')[0, 0]), 0.2, places=6)
        # Al revés: si aquí está el más nuevo, lo traído se descarta y su carpeta se borra.
        with self.other.db:
            self.other.db.execute("UPDATE productos_escena SET fecha_proceso='2025-12-31 00:00:00'")
        root = paste(self.other, self.cat)
        report = sync(self.cat, AOI)
        self.assertEqual((report['reemplazados'], len(report['omitidos'])), ([], 1))
        self.assertFalse(root.exists())
        self.assertAlmostEqual(float(read_band(self.cat.storage/rows[0]['carpeta']/'chl_oc3.tif')[0, 0]), 0.2, places=6)

    def test_broken_folder_is_not_imported_and_pasted_catalog_is_kept(self):
        product(self.other, scene(self.other, SCENE, 'PROCESADA'))
        root = paste(self.other, self.cat)
        missing = next(root.rglob('chl_oc3.tif'))
        missing.unlink()
        report = sync(self.cat, AOI)
        self.assertEqual(len(report['errores']), 1)
        self.assertIn('falta chl_oc3.tif', report['errores'][0])
        self.assertEqual(self.count('SELECT count(*) FROM productos_escena'), 0)
        self.assertFalse(report['catalogo_borrado'])
        self.assertTrue((root/'catalog.sqlite').exists())
        self.assertIn('calidad.tif', ' '.join(report['restos']))

    def test_requires_pasted_catalog_of_supported_version(self):
        with self.assertRaisesRegex(ValueError, 'pegue'):
            sync(self.cat, AOI)
        root = paste(self.other, self.cat)
        with contextlib.closing(sqlite3.connect(root/'catalog.sqlite')) as db:
            db.execute('PRAGMA user_version=5')
            db.commit()
        with self.assertRaisesRegex(ValueError, 'v5'):
            sync(self.cat, AOI)

    def test_cli_sync_recomputes_derived_products_of_synced_sensors(self):
        from oceanos.cli import main
        product(self.other, scene(self.other, SCENE, 'PROCESADA'))
        paste(self.other, self.cat)
        self.cat.db.close()
        with patch('oceanos.cli.derived_products') as derived:
            code = main(['--storage', str(self.cat.storage), 'sync'])
        self.cat = Catalog(self.cat.storage)
        self.assertEqual(code, 0)
        self.assertEqual([call.args[1]['family'] for call in derived.call_args_list], ['sentinel2'])
        self.assertEqual(self.count('SELECT count(*) FROM productos_escena'), 1)


if __name__ == '__main__':
    unittest.main()
