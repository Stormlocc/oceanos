"""Pruebas de comportamiento del catálogo y del wrapper; no duplican ciencia ACOLITE."""
import json
import os
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from oceanos.catalog import Catalog
from oceanos.config import ACOLITE, PROFILE, profile, exclusive
from oceanos.native import scene_identity, eligible, extract
from oceanos.pipeline import Pipeline, cleanup, recover
import sin_red

# Sin red en las pruebas: unittest llama estos hooks del módulo.
setUpModule, tearDownModule = sin_red.setUpModule, sin_red.tearDownModule

SCENE='S2B_MSIL1C_20260804T150719_N0512_R082_T19QGV_20260804T182348.SAFE'
# Intervalo fijo de las pruebas: independiente del intervalo de trabajo del YAML.
START,END='2026-08-01T00:00:00Z','2026-08-15T00:00:00Z'


def source(checksum='a', **extra):
    return {'provider':'CDSE','product':SCENE,'format':'SAFE','id':'public-id',
            'identity':scene_identity(SCENE),'metadata':{'Checksum':[{'Algorithm':'MD5','Value':checksum}]},**extra}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cat=Catalog(self.temp.name)
        self.config=profile(PROFILE,'sentinel2',start=START,end=END)

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def scene(self, data=None):
        return self.cat.upsert_scene(data or source())

    def test_status_lists_processes_filters_and_detail(self):
        name=self.scene()
        first=self.cat.start(name,'DESCARGA',self.config);self.cat.finish(first,'FALLIDO',error='TimeoutError')
        second=self.cat.start(name,'DESCARGA',self.config)
        self.cat.finish(second,'OK','TECNICA_OK',metrics=[{'stage':'process','seconds':1,'ok':True}])
        self.cat.record_product(name,'ponce_guayanilla','water2coast_v1',proceso=second,estado='OK',sensor='S2')
        self.assertEqual((first,second),(1,2))
        self.assertIsNone(self.cat.process(second)['carpeta'])
        rows=self.cat.runs()
        self.assertEqual([(r['id'],r['satelite'],r['zonas_ok']) for r in rows],[(1,'S2B',0),(2,'S2B',1)])
        self.assertEqual([(r['id'],r['error']) for r in self.cat.runs('FALLIDO')],[(1,'TimeoutError')])
        self.assertEqual([r['id'] for r in self.cat.runs(last=1)],[2])
        self.assertEqual(self.cat.runs(legacy=True),[])
        detail=self.cat.run_detail('0002')
        self.assertEqual(detail['metricas'][0]['stage'],'process');self.assertNotIn('detalle',detail)
        self.assertTrue(detail['eventos'][0].endswith('INICIO: Proceso descarga de '+SCENE))
        with self.assertRaises(ValueError): self.cat.run_detail('zz')

    def test_scene_columns_are_readable_and_search_keeps_state(self):
        data=source(metadata={'Checksum':[{'Algorithm':'MD5','Value':'a'}],'ContentLength':789_574_421,
                              'ContentDate':{'Start':'2026-08-04T15:07:19Z'},'Attributes':[{'Name':'cloudCover','Value':2.3559}]})
        name=self.scene(data);self.cat.enqueue([name]);self.scene(data)
        row=self.cat.db.execute('SELECT * FROM escenas').fetchone()
        self.assertEqual((row['sensor'],row['satelite'],row['fecha_utc'],row['tile'],row['tamano_mb'],row['nubosidad'],row['estado']),
                         ('sentinel2','S2B','2026-08-04 15:07','19QGV',789.6,2.36,'PENDIENTE'))
        self.assertEqual(self.cat.db.execute('SELECT count(*) FROM escenas').fetchone()[0],1)

    def test_content_change_drops_verified_sha(self):
        self.scene(source(sha256='old'))
        self.assertEqual(self.scene(source())and self.cat.source(SCENE)['sha256'],'old')
        self.scene(source('b'))
        self.assertNotIn('sha256',self.cat.source(SCENE))
        self.assertEqual(self.cat.db.execute("SELECT count(*) FROM eventos WHERE tipo='CONTENIDO_CAMBIADO'").fetchone()[0],1)

    def test_resolve_scene_by_fragment(self):
        self.scene();other=SCENE.replace('20260804T150719','20260809T150719')
        self.scene({**source(),'product':other,'identity':scene_identity(other)})
        self.assertEqual(self.cat.resolve_scene('20260809T'),other)
        with self.assertRaises(ValueError): self.cat.resolve_scene('S2B_MSIL1C')
        with self.assertRaises(ValueError): self.cat.resolve_scene('nada')

    def raw(self, process):
        raw=self.cat.storage/'temporary'/str(process);raw.mkdir(parents=True);(raw/'partial.zip').touch()
        return raw

    def interrupted(self, state=None):
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        raw=self.raw(process)
        if state: self.cat.finish(process,state)
        return process,raw

    def test_interruption_is_cleaned_by_recover(self):
        process,raw=self.interrupted()
        self.assertEqual(self.cat.recover(),1)
        self.assertEqual(cleanup(self.cat,process),'HECHA')
        self.assertFalse(raw.exists())
        self.assertEqual(self.cat.process(process)['estado'],'INTERRUMPIDO')

    def test_failed_process_keeps_download_until_reused(self):
        process,raw=self.interrupted('FALLIDO')
        self.assertEqual(cleanup(self.cat,process),'APLAZADA')
        self.assertTrue((raw/'partial.zip').exists())
        self.assertEqual(cleanup(self.cat,process,force=True),'HECHA')
        self.assertFalse(raw.exists())
        self.assertEqual(self.cat.process(process)['estado'],'FALLIDO')

    def test_recover_cleans_hard_stop_and_ctrl_c(self):
        hard,hard_raw=self.interrupted()
        ctrl_c,ctrl_raw=self.interrupted('INTERRUMPIDO')
        _,failed_raw=self.interrupted('FALLIDO')
        result=recover(self.cat)
        self.assertEqual(result['interrumpidos'],1)
        self.assertEqual(sorted(result['limpiados']),[hard,ctrl_c])
        self.assertFalse(hard_raw.exists());self.assertFalse(ctrl_raw.exists())
        self.assertTrue(failed_raw.exists())
        self.assertEqual(recover(self.cat),{'interrumpidos':0,'limpiados':[],'limpieza_fallida':[]})

    def test_recover_continues_when_cleanup_fails(self):
        locked,locked_raw=self.interrupted()
        with patch('oceanos.pipeline.shutil.rmtree',side_effect=OSError):
            result=recover(self.cat)
        self.assertEqual(result['limpieza_fallida'],[locked])
        self.assertEqual(self.cat.process(locked)['limpieza'],'FALLIDA')
        self.assertTrue(locked_raw.exists())
        self.assertEqual(recover(self.cat)['limpiados'],[locked])
        self.assertFalse(locked_raw.exists())

    def test_cleanup_rejects_escape_and_preserves_success(self):
        process=self.cat.start(self.scene(),'DESCARGA',self.config);self.cat.finish(process,'INTERRUMPIDO')
        outside=Path(self.temp.name)/'outside';outside.mkdir();(outside/'keep').touch()
        (self.cat.storage/'temporary').mkdir();(self.cat.storage/'temporary'/str(process)).symlink_to(outside)
        with self.assertRaises(ValueError): cleanup(self.cat,process)
        self.assertTrue((outside/'keep').exists())
        ok=self.cat.start(self.scene(),'DESCARGA',self.config);self.raw(ok)
        self.cat.finish(ok,'OK','TECNICA_OK')
        self.assertEqual(cleanup(self.cat,ok),'HECHA')
        self.assertEqual(self.cat.process(ok)['estado'],'OK')

    def test_cleanup_failure_does_not_repeat_processing(self):
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        self.raw(process)
        self.cat.finish(process,'OK','TECNICA_OK')
        with patch('oceanos.pipeline.shutil.rmtree',side_effect=OSError):
            with self.assertRaises(OSError): cleanup(self.cat,process)
        row=self.cat.process(process)
        self.assertEqual((row['estado'],row['limpieza']),('OK','FALLIDA'))
        self.assertEqual(cleanup(self.cat,process),'HECHA')

    def test_exclusive_writer(self):
        with exclusive(self.cat.storage):
            with self.assertRaises(RuntimeError):
                with exclusive(self.cat.storage): pass

    def test_old_catalog_is_backed_up_and_views_work(self):
        import sqlite3
        folder=Path(self.temp.name)/'old';(folder/'catalog').mkdir(parents=True)
        db=sqlite3.connect(folder/'catalog/catalog.sqlite')
        db.execute('CREATE TABLE ejecuciones(id TEXT)');db.execute('PRAGMA user_version=3');db.commit();db.close()
        cat=Catalog(folder)
        self.assertTrue(cat.backup.name.startswith('catalog_v3_respaldo_') and cat.backup.exists())
        self.assertFalse(cat.migrated)
        views=[r[0] for r in cat.db.execute("SELECT name FROM sqlite_master WHERE type='view'")]
        self.assertTrue({'v_superimagen','v_compuestos','v_legado','v_cola'} <= set(views))
        for view in views:
            cat.db.execute(f'SELECT * FROM {view}').fetchall()
        self.assertEqual(cat.db.execute('PRAGMA user_version').fetchone()[0],5)
        cat.db.close()
        self.assertIsNone(Catalog(folder).backup)

    def test_v4_catalog_is_migrated_with_backup_and_legacy(self):
        name=self.scene();self.cat.enqueue([name])
        legacy=self.cat.start(name,'DESCARGA',{'aoi':{'id':'lapargera_v1'}});self.cat.finish(legacy,'OK','TECNICA_OK')
        db=self.cat.db
        for (view,) in db.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall():
            db.execute(f'DROP VIEW {view}')
        db.execute('DROP INDEX productos_zona')
        for table in ('compuesto_escenas','compuestos','productos_escena','mascaras'):
            db.execute(f'DROP TABLE {table}')
        for table,column in (('escenas','zonas'),('procesos','legado'),('busquedas','aoi')):
            db.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
        db.execute('PRAGMA user_version=4');db.commit();db.close()
        self.cat=Catalog(self.temp.name)
        self.assertTrue(self.cat.migrated and self.cat.backup.name.startswith('catalog_v4_respaldo_'))
        self.assertEqual(self.cat.process(legacy)['legado'],1)
        self.assertEqual(self.cat.legacy_count(),1)
        self.assertEqual(self.cat.db.execute('SELECT estado FROM escenas').fetchone()[0],'NUEVA')
        self.assertEqual(self.cat.runs(),[])
        self.assertEqual([r['id'] for r in self.cat.legacy()],[legacy])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.config=profile(PROFILE,'sentinel2',start=START,end=END)

    def test_date_boundaries(self):
        def dated(date):
            return source(identity={**scene_identity(SCENE),'date':date})
        self.assertTrue(eligible(dated('20260801T000000'),self.config))
        self.assertFalse(eligible(dated('20260821T000000'),self.config))
        self.assertFalse(eligible(dated('20260731T235959'),self.config))

    def test_products_outside_the_sensor_profile_are_rejected(self):
        with self.assertRaises(ValueError): profile(PROFILE,'sentinel2',['chl_oc4'])
        with self.assertRaises(ValueError): profile(PROFILE,'landsat',['ndci'])
        with self.assertRaises(ValueError): profile(PROFILE,'sentinel2',['fai',''])
        override=profile(PROFILE,'sentinel2',[' fai','ndvi','fai'])
        self.assertEqual(override['products'],['fai','ndvi'])
        for zone in override['zones'].values():
            self.assertEqual(zone['native']['l2w_parameters'],'fai,ndvi')

    def test_zone_settings_project_to_aligned_zone_grid(self):
        self.assertEqual(list(self.config['zones']),['mayaguez_cabo_rojo','la_parguera_guanica','ponce_guayanilla','fajardo_culebra'])
        fajardo=self.config['zones']['fajardo_culebra']
        native,grid=fajardo['native'],fajardo['grid']
        self.assertEqual((grid['epsg'],grid['resolution_m']),(32620,10))
        self.assertTrue(all(value%10==0 for value in grid['xrange_m']+grid['yrange_m']))
        self.assertEqual(native['region_name'],'fajardo_culebra')
        self.assertEqual((native['output_projection_epsg'],native['reproject_before_ac'],native['output_projection_resampling_method']),
                         ('32620','True','nearest'))
        self.assertEqual((native['dsf_residual_glint_correction'],native['glint_write_rhog_ref']),('True','True'))
        self.assertEqual(fajardo['places'],['20QKF'])
        landsat=profile(PROFILE,'landsat',start='2026-08-01',end='2026-08-15')
        self.assertEqual(landsat['zones']['fajardo_culebra']['grid']['resolution_m'],30)
        self.assertTrue(all(v%30==0 for v in landsat['zones']['ponce_guayanilla']['grid']['xrange_m']))
        self.assertEqual(profile(PROFILE,'olci')['zones']['ponce_guayanilla']['grid']['resolution_m'],300)

    def test_zone_selection(self):
        config=profile(PROFILE,'sentinel2',start=START,end=END,zones=['ponce_guayanilla'])
        self.assertEqual(list(config['zones']),['ponce_guayanilla'])
        with self.assertRaises(ValueError): profile(PROFILE,'sentinel2',zones=['culebrita'])

    def test_scene_is_assigned_to_zones_by_tile_and_footprint(self):
        from oceanos.native import zones_for
        self.assertEqual(zones_for(source(),self.config),['la_parguera_guanica','ponce_guayanilla'])
        ponce=self.config['zones']['ponce_guayanilla']['wkt']
        from osgeo import ogr
        footprint=json.loads(ogr.CreateGeometryFromWkt(ponce).Centroid().Buffer(0.01).ExportToJson())
        self.assertEqual(zones_for(source(footprint=footprint),self.config),['ponce_guayanilla'])
        other=source(identity={**scene_identity(SCENE),'tile':'19QHA'})
        self.assertEqual(zones_for(other,self.config),[])
        self.assertFalse(eligible(other,self.config))

    def test_archive_traversal_is_rejected_before_native_extraction(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            archive=Path(tmp)/'input.zip'
            with zipfile.ZipFile(archive,'w') as z: z.writestr('../outside','bad')
            ac=Mock()
            with self.assertRaises(ValueError): extract(ac,archive,Path(tmp)/'raw',1000)
            ac.shared.extract_bundle.assert_not_called()

    def test_query_retries_are_recorded_then_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            cat=Catalog(tmp)
            runner=object.__new__(Pipeline);runner.catalog=cat;runner.config=self.config
            waits=[];runner.wait=waits.append
            providers=[]
            def fake(operation,**args):
                providers.append(args['provider']);raise TimeoutError()
            runner.call=fake
            with self.assertRaises(TimeoutError): runner.search()
            self.assertEqual(providers,['CDSE']*3)
            self.assertEqual(waits,[10,30])
            self.assertEqual(cat.db.execute("SELECT count(*) FROM busquedas WHERE estado='FALLIDA' AND aoi='water2coast_v1'").fetchone()[0],3)
            cat.db.close()

    def test_native_patch_preserves_default_return_and_exposes_metadata(self):
        # Ejecutar la función auditada con red simulada, incluida su paginación.
        from oceanos.native import load
        ac=load(ACOLITE)
        first={'value':[{'Id':'one','Name':SCENE,'Attributes':[], 'Checksum':[]}], '@odata.nextLink':'https://example.com/page2'}
        second={'value':[{'Id':'two','Name':SCENE,'Attributes':[]}]}
        def response(data):
            r=Mock();r.status_code=200;r.json.return_value=data;return r
        with patch('requests.get',side_effect=[response(first),response(second)]):
            result=ac.api.cdse.query(scene=SCENE,attributes=True,return_metadata=True,verbosity=0)
            self.assertEqual([m['Id'] for m in result[2]],['one','two'])
        with patch('requests.get',return_value=response({'value':[]})):
            self.assertEqual(ac.api.cdse.query(scene=SCENE,verbosity=0),([],[]))
        with patch('requests.get',return_value=response({'error':'bad'})):
            with self.assertRaises(ValueError): ac.api.cdse.query(scene=SCENE,verbosity=0)


GRID={'epsg':32619,'resolution_m':10,'xrange_m':[0,20],'yrange_m':[20,0],'shape_yx':[2,2],'geotransform':[0,10,0,20,0,-10]}


class ValidationTests(unittest.TestCase):
    def setUp(self):
        import netCDF4
        import numpy as np
        from pyproj import CRS
        self.temp=tempfile.TemporaryDirectory()
        self.products=['Rrs_*','chl_oc3']
        self.files={}
        for level in ['l2r','l2w']:
            path=Path(self.temp.name)/(level+'.nc');self.files[level]=str(path)
            with netCDF4.Dataset(path,'w') as ds:
                ds.createDimension('x',2);ds.createDimension('y',2)
                ds.createVariable('x','f8',('x',))[:]=[5,15]
                ds.createVariable('y','f8',('y',))[:]=[15,5]
                crs=ds.createVariable('crs','i4');crs.crs_wkt=CRS.from_epsg(32619).to_wkt()
                ds.acolite_file_type=level.upper()
                names=['rhot_665','rhos_665'] if level=='l2r' else ['Rrs_665','chl_oc3']
                for name in names: ds.createVariable(name,'f4',('y','x'))[:]=np.nan
                if level=='l2w': ds.createVariable('l2_flags','i4',('y','x'))[:]=1

    def tearDown(self): self.temp.cleanup()

    def test_all_masked_is_technical_success_but_science_pending(self):
        from oceanos.validation import validate
        report=validate(self.files,GRID,self.products)
        self.assertEqual(report['technical'],'PASSED')
        self.assertEqual(report['scientific'],'PENDING')
        self.assertEqual(report['finite_pixels']['chl_oc3']['count'],0)

    def test_shifted_grid_rejected(self):
        import netCDF4
        from oceanos.validation import validate
        with netCDF4.Dataset(self.files['l2w'],'a') as ds: ds['x'][:]=[10,20]
        with self.assertRaises(ValueError): validate(self.files,GRID,self.products)

    def test_other_projection_rejected(self):
        from oceanos.validation import validate
        with self.assertRaises(ValueError): validate(self.files,{**GRID,'epsg':32620},self.products)

    def test_missing_requested_product_rejected(self):
        from oceanos.validation import validate
        with self.assertRaises(ValueError): validate(self.files,GRID,self.products+['ndci'])

    def test_fai_is_not_satisfied_by_fait(self):
        from oceanos.validation import product_variables
        self.assertEqual(product_variables('fai',['fait','FAI']),['FAI'])
        self.assertEqual(product_variables('tur_nechad2009',['TUR_Nechad2009_665']),['TUR_Nechad2009_665'])

    def test_incomplete_rrs_wildcard_rejected(self):
        import netCDF4
        from oceanos.validation import validate
        with netCDF4.Dataset(self.files['l2r'],'a') as ds: ds.createVariable('rhos_560','f4',('y','x'))[:]=0
        with self.assertRaises(ValueError): validate(self.files,GRID,self.products)



L2W='S2B_MSI_2026_08_04_15_08_03_T19QGV_lapargera_v1_L2W.nc'
L1R='S2B_MSI_2026_08_04_15_08_03_T19QGV_lapargera_v1_L1R.nc'


class QueueSyncTests(unittest.TestCase):
    """Legado importado por nombre, cola de run, tiempos de descarga y resumen."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cat=Catalog(self.temp.name)
        self.config=profile(PROFILE,'sentinel2',start=START,end=END)
        self.imports=self.cat.storage/'importados';self.imports.mkdir()

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def scene(self, data=None):
        name=self.cat.upsert_scene(data or source())
        self.cat.set_zones(name,['la_parguera_guanica','ponce_guayanilla'])
        return name

    def named(self, date):
        name=SCENE.replace('20260804T150719',date)
        return self.scene({**source(),'product':name,'identity':scene_identity(name)})

    def runner(self):
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config
        runner.engine={};runner.metrics=[];runner.wait=lambda _:None
        return runner

    def finish_zones(self, scene, zones=('la_parguera_guanica','ponce_guayanilla'), state='OK'):
        for zone in zones:
            self.cat.record_product(scene,zone,'water2coast_v1',estado=state,sensor='S2',fecha='2026-08-04')

    def test_output_name_matches_provider_acquisition(self):
        from oceanos.native import output_identity, acquisition_day
        info=output_identity(L2W)
        self.assertEqual((info['region'],info['level']),('lapargera_v1','L2W'))
        self.assertEqual(info['acquisition_key'],acquisition_day(scene_identity(SCENE)))
        landsat=output_identity('L9_OLI_2026_08_05_14_57_33_004047_L1R.nc')
        self.assertEqual(landsat['acquisition_key'],acquisition_day(scene_identity('LC09_L1TP_004047_20260805_20260806_02_T1')))
        with self.assertRaises(ValueError): output_identity('notas.nc')

    def test_sync_registers_legacy_that_never_counts_as_done(self):
        from oceanos.sync import sync
        name=self.scene();self.cat.enqueue([name])
        (self.imports/L2W).write_bytes(b'l2w');(self.imports/L1R).write_bytes(b'l1r');(self.imports/'otro.nc').write_bytes(b'x')
        report=sync(self.cat,self.imports)
        self.assertEqual(sorted(i['tipo'] for i in report['importados']),['L1R','L2W'])
        self.assertEqual(report['no_reconocidos'],['importados/otro.nc'])
        process=report['importados'][0]['proceso']
        row=self.cat.process(process)
        self.assertEqual((row['tipo'],row['estado'],row['validacion'],row['escena'],row['carpeta'],row['limpieza'],row['legado']),
                         ('IMPORTADO','IMPORTADO','SIN_VERIFICAR',name,'importados','NO_APLICA',1))
        self.assertIsNone(row['l2w_sha256'])
        # El legado no saca la escena de la cola ni cuenta como "ya lo tenemos".
        self.assertEqual(self.cat.db.execute('SELECT estado FROM escenas').fetchone()[0],'PENDIENTE')
        self.assertEqual(self.cat.completed('water2coast_v1'),{})
        self.assertEqual(self.cat.completed('lapargera_v1'),{})
        self.assertEqual([r['id'] for r in self.cat.legacy()],[process])
        again=sync(self.cat,self.imports)
        self.assertEqual((again['importados'],again['ya_registrados']),([],2))
        (self.imports/L2W).unlink()
        self.assertEqual(sync(self.cat,self.imports)['desaparecidos'],['importados/'+L2W])
        (self.imports/L2W).write_bytes(b'l2w')
        self.assertEqual(sync(self.cat,self.imports)['reaparecidos'],['proceso 1 (importados)'])
        self.assertEqual(cleanup(self.cat,process),'NO_APLICA')
        self.assertTrue((self.imports/L2W).exists())

    def test_sync_late_l1r_completes_same_process(self):
        from oceanos.sync import sync
        (self.imports/L2W).write_bytes(b'l2w');first=sync(self.cat,self.imports)['importados'][0]['proceso']
        (self.imports/L1R).write_bytes(b'l1r');second=sync(self.cat,self.imports)['importados'][0]['proceso']
        self.assertEqual(first,second)
        self.assertEqual(self.cat.db.execute('SELECT count(*) FROM procesos').fetchone()[0],1)

    def test_sync_without_provider_scene_creates_local_one(self):
        from oceanos.sync import sync
        (self.imports/L2W).write_bytes(b'l2w')
        sync(self.cat,self.imports)
        row=self.cat.db.execute('SELECT escena,proveedor,satelite,fecha_utc FROM escenas').fetchone()
        self.assertEqual(tuple(row),('S2B_20260804_19QGV','LOCAL','S2B','2026-08-04 15:08'))

    def test_provider_scene_absorbs_local_scene_from_sync(self):
        from oceanos.sync import sync
        (self.imports/L2W).write_bytes(b'l2w');sync(self.cat,self.imports)
        name=self.scene()
        self.assertEqual([r[0] for r in self.cat.db.execute('SELECT escena FROM escenas')],[name])
        self.assertEqual(self.cat.process(1)['escena'],name)

    def test_sync_adopts_runs_with_readable_names(self):
        from oceanos.sync import sync
        old=self.cat.storage/'runs'/'0df48287585d47b8aa4643234003e5a0'/'output';old.mkdir(parents=True)
        (old/L2W).write_bytes(b'l2w');(old/L1R).write_bytes(b'l1r')
        report=sync(self.cat,self.cat.storage/'runs',hashed=True)
        row=self.cat.process(1)
        folder="runs/0001_S2B_2026-08-04"
        self.assertEqual((row['carpeta'],row['l2w'],row['legado']),(folder,folder+'/'+L2W,1))
        self.assertTrue(row['l2w_sha256'])
        self.assertEqual(sorted(p.name for p in (self.cat.storage/row['carpeta']).iterdir()),[L1R,L2W])
        self.assertEqual(len(report['importados']),2)
        self.assertEqual(sync(self.cat,self.cat.storage/'runs')['ya_registrados'],2)

    def test_sync_rejects_folders_outside_or_reserved(self):
        from oceanos.sync import sync
        for folder in ('temporary','catalog','superimagen','auxiliares'):
            (self.cat.storage/folder).mkdir(exist_ok=True)
        for folder in (self.cat.storage/'temporary',self.cat.storage/'catalog',self.cat.storage/'superimagen',
                       self.cat.storage,Path(tempfile.gettempdir())):
            with self.assertRaises(ValueError): sync(self.cat,folder)

    def test_queue_pending_skips_completed_zones_and_out_of_profile(self):
        inside=self.scene();later=self.named('20260809T150719');outside=self.named('20260901T150719')
        self.cat.enqueue([inside,later,outside])
        self.finish_zones(inside)
        ready,out,available,deferred=self.cat.pending(self.config)
        self.assertEqual((ready,out,available,deferred),([later],[outside],[inside],[]))
        self.assertEqual({i['escena']:i['estado'] for i in self.cat.queue()}[inside],'DISPONIBLE')
        self.cat.dequeue(outside)
        self.assertNotIn(outside,[i['escena'] for i in self.cat.queue()])
        self.assertEqual(self.cat.pending(self.config,force=True)[2],[])

    def test_one_zone_left_keeps_the_acquisition_pending(self):
        name=self.scene();self.cat.enqueue([name])
        self.finish_zones(name,['ponce_guayanilla'],'NUBOSA')
        self.assertEqual(self.cat.pending(self.config)[0],[name])
        only_ponce=profile(PROFILE,'sentinel2',start=START,end=END,zones=['ponce_guayanilla'])
        self.assertEqual(self.cat.pending(only_ponce)[2],[name])

    def test_batch_updates_scene_states_and_returns_summary(self):
        ok=self.scene();bad=self.named('20260809T150719')
        self.cat.enqueue([ok,bad])
        runner=self.runner()
        def fake(scene,force=False):
            runner.current_run=self.cat.start(scene,'DESCARGA',self.config)
            if scene==bad:
                self.cat.finish(runner.current_run,'FALLIDO',error='RuntimeError');raise RuntimeError('fallo')
            self.cat.finish(runner.current_run,'OK','TECNICA_OK')
            return runner.current_run
        runner.run=fake
        result=runner.batch([ok,bad])
        self.assertEqual((result['failed'],result['runs']),([bad],[1,2]))
        self.assertEqual({i['escena']:i['estado'] for i in self.cat.queue()},{ok:'PROCESADA',bad:'FALLIDA'})
        self.assertEqual(self.cat.pending(self.config)[0],[bad])
        self.assertEqual([r['escena'] for r in self.cat.db.execute('SELECT escena FROM v_fallidas')],[bad])

    def test_download_time_size_and_attempts_recorded(self):
        runner=self.runner()
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        self.cat.event('INTENTO_FALLIDO','intento 1',process)
        runner.metrics=[{'stage':'acquire','seconds':8.0,'ok':False},{'stage':'acquire','seconds':120.5,'ok':True}]
        archive=self.cat.storage/'scene.zip';archive.write_bytes(b'x'*4_200_000)
        runner.record_download(process,archive,source())
        row=self.cat.process(process)
        self.assertEqual((row['descarga_min'],row['descarga_mb'],row['intentos']),(2.01,4.2,2))

    def cli_run(self, argv, pipeline):
        from oceanos import cli
        with patch('oceanos.cli.Pipeline',return_value=pipeline),patch('oceanos.cli.ensure_masks') as masks, \
             patch('oceanos.cli.derived_products') as derived,patch('sys.stdout'):
            code=cli.main(['--storage',self.temp.name,'--sensor','sentinel2','--start',START,'--end',END]+argv)
        return code,masks,derived

    def test_plan_searches_without_registering_or_downloading(self):
        name=self.scene()
        pipeline=Mock(last_query=None);pipeline.search.return_value=[name]
        code,masks,derived=self.cli_run(['run','--plan'],pipeline)
        self.assertEqual(code,0)
        pipeline.search.assert_called_once();pipeline.batch.assert_not_called()
        masks.assert_not_called();derived.assert_not_called()
        self.assertEqual(self.cat.queue(),[])

    def test_run_searches_registers_processes_and_derives(self):
        name=self.scene()
        pipeline=Mock(last_query=None);pipeline.search.return_value=[name]
        pipeline.batch.return_value={'runs':[],'failed':[],'seconds':1}
        code,masks,derived=self.cli_run(['run'],pipeline)
        self.assertEqual(code,0)
        masks.assert_called_once();derived.assert_called_once()
        pipeline.batch.assert_called_once_with([name],force=False)
        self.assertEqual([i['escena'] for i in self.cat.queue()],[name])

    def test_run_with_scene_does_not_search(self):
        name=self.scene()
        pipeline=Mock(last_query=None);pipeline.batch.return_value={'runs':[],'failed':[],'seconds':1}
        self.cli_run(['run','--escena','20260804'],pipeline)
        pipeline.search.assert_not_called()
        pipeline.batch.assert_called_once_with([name],force=False)

    def test_search_registers_only_when_asked(self):
        from oceanos import cli
        name=self.scene();pipeline=Mock(last_query=None);pipeline.search.return_value=[name]
        for argv,queued in ((['search'],0),(['search','--registrar'],1)):
            with patch('oceanos.cli.Pipeline',return_value=pipeline),patch('sys.stdout'):
                self.assertEqual(cli.main(['--storage',self.temp.name,'--sensor','sentinel2','--start',START,'--end',END]+argv),0)
            self.assertEqual(len(self.cat.queue()),queued)

    def test_search_table_shows_date_size_zones_and_scene(self):
        import io, contextlib
        from oceanos import cli
        name=self.scene(source(metadata={'ContentLength':582984789,'ContentDate':{'Start':'2026-08-04T15:07:19Z'}}))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rows=cli.scene_rows(self.cat,[name],self.config)
            cli.show_versions(rows)
            cli.show_estimate(self.cat,self.config,rows)
        self.assertEqual((rows[0]['fecha_utc'],rows[0]['tamano'],rows[0]['estado'],rows[0]['zonas']),
                         ('2026-08-04 15:07','583.0 MB','NUEVA','la_parguera_guanica,ponce_guayanilla'))
        self.assertIn(SCENE,out.getvalue());self.assertIn('2 productos de zona',out.getvalue())

    def test_progress_without_terminal_prints_periodic_lines(self):
        import io
        from oceanos.progress import Progress, size, duration
        stream=io.StringIO();bar=Progress(stream,interactive=False,every=0)
        bar.scene(1,2,'S2B 2026-08-04')
        bar.download(250_000_000,500_000_000,5_000_000,50)
        bar.stage('ACOLITE',90,180)
        text=stream.getvalue()
        self.assertIn('Escena 1 de 2',text);self.assertIn('50.0%',text);self.assertIn('quedan 50s',text)
        self.assertIn('~ 50%',text)
        self.assertEqual((size(3_614_650_739),duration(3725)),('3.6 GB','1h02m05s'))


class SelectionTests(unittest.TestCase):
    """--sensor, --satelite y --zona en search/run, y ayudas con valores válidos."""
    def test_satellite_filter_restricts_profile_platforms(self):
        config=profile(PROFILE,'sentinel2',start=START,end=END,satellites=['S2C'])
        self.assertEqual(config['search']['platforms'],['S2C'])
        self.assertFalse(eligible(source(),config))
        with self.assertRaises(ValueError): profile(PROFILE,'sentinel2',satellites=['L8'])

    def test_landsat_platform_is_checked(self):
        name='LC09_L1TP_005048_20260805_20260806_02_T1'
        data={'provider':'USGS','product':name,'format':'TAR','identity':scene_identity(name),'metadata':{}}
        self.assertTrue(eligible(data,profile(PROFILE,'landsat')))
        self.assertFalse(eligible(data,profile(PROFILE,'landsat',satellites=['L8'])))

    def test_sensor_satellite_and_zone_accepted_before_or_after_command(self):
        from oceanos import cli
        for argv in (['--sensor','landsat','--satelite','l9','search'],['search','--sensor','landsat','--satelite','LC09']):
            args=cli.parser().parse_args(argv)
            self.assertEqual((args.sensor,args.satelite),('landsat',['L9']))
            self.assertEqual([c['search']['platforms'] for c in cli.load_profiles(args)],[['L9']])
        args=cli.parser().parse_args(['--satelite','S2B','run','--start','2026-08-01','--end','2026-08-15','--zona','ponce_guayanilla'])
        self.assertEqual((args.satelite,args.start,args.sensor),(['S2B'],'2026-08-01',None))
        configs=cli.load_profiles(args)
        self.assertEqual([(c['family'],list(c['zones'])) for c in configs],[('sentinel2',['ponce_guayanilla'])])
        self.assertEqual([c['family'] for c in cli.load_profiles(cli.parser().parse_args(['run']))],
                         ['sentinel2','landsat','olci'])
        with self.assertRaises(ValueError):
            cli.load_profiles(cli.parser().parse_args(['search','--sensor','landsat','--satelite','S2B']))

    def test_invalid_values_are_rejected_with_options(self):
        import io, contextlib
        from oceanos import cli
        for argv,hint in ((['search','--satelite','S2D'],'S2A, S2B, S2C'),(['--start','2026-13-01','search'],'AAAA-MM-DD'),
                          (['search','--sensor','modis'],'sentinel2')):
            err=io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit): cli.parser().parse_args(argv)
            self.assertIn(hint,err.getvalue())
        with self.assertRaises(ValueError) as caught: profile(PROFILE,'sentinel2',['chl_oc4'])
        self.assertIn('chl_oc3',str(caught.exception))


LANDSAT='LC09_L1TP_005048_20260805_20260806_02_T1'
NEIGHBOR='LC08_L1TP_006048_20260813_20260814_02_T1'


class UsgsQueryTests(unittest.TestCase):
    """Información de search para Landsat: tamaño, completitud, descartes y fecha."""
    def setUp(self):
        self.config=profile(PROFILE,'landsat',start='2026-08-01',end='2026-08-21')

    def ac(self, names):
        ac=Mock();ac.config={'EARTHEXPLORER_api':'https://m2m.example/api'}
        ac.api.earthexplorer.auth.return_value='token'
        attrs=[{'fieldName':'Start Time','value':'2026-08-05 14:57:33'}]
        found=[{'entity':n[:4]+'ENT'+str(i),'product':n,'dataset':'landsat_ot_c2_l1','metadata':attrs} for i,n in enumerate(names)]
        search=patch('oceanos.native.usgs_search',return_value=(found,None));search.start();self.addCleanup(search.stop)
        return ac

    def test_query_explains_exclusions_sizes_and_unknown_completeness(self):
        from oceanos import native
        ac=self.ac([LANDSAT,NEIGHBOR,'LC09_L1GT_005048_20260805_20260806_02_T2'])
        with patch('oceanos.native.usgs_sizes',return_value=({'LC09ENT0':912_345_678},None)) as sizes:
            result=native.query(ac,'USGS',self.config)
        self.assertEqual(result['sizes'],'M2M')
        sizes.assert_called_once_with(ac,'landsat_ot_c2_l1',['LC09ENT0'])
        self.assertEqual([s['product'] for s in result['sources']],[LANDSAT])
        self.assertEqual(native.l1_bytes(result['sources'][0]),912_345_678)
        self.assertEqual(result['completeness'],'UNKNOWN');self.assertEqual(result['returned'],3)
        reasons={e['product']:e['reason'] for e in result['excluded_by_profile']}
        self.assertIn('path/row 006/048 fuera de los path/row de las zonas',reasons[NEIGHBOR])
        self.assertIn('L1TP',reasons['LC09_L1GT_005048_20260805_20260806_02_T2'])
        self.assertEqual(native.scene_date(result['sources'][0]),'2026-08-05 14:57')

    def test_usgs_search_follows_pages_until_total_hits(self):
        import requests
        from oceanos.native import usgs_search, usgs_completeness
        ac=Mock();ac.config={'EARTHEXPLORER_api':'https://m2m.example/api'};ac.api.earthexplorer.auth.return_value='token'
        ac.shared.roi_wkt.return_value='POLYGON ((-67.2 17.9, -66.9 17.9, -66.9 18.0, -67.2 18.0, -67.2 17.9))'
        scene=lambda i: {'entityId':f'E{i}','metadata':[{'fieldName':'Landsat Product Identifier L2','value':'L2'},
                                                         {'fieldName':'Landsat Product Identifier L1','value':f'P{i}'}]}
        pages=[{'data':{'totalHits':5,'totalHitsAccuracy':'calculated','results':[scene(1),scene(2)],'nextRecord':3}},
               {'data':{'totalHits':5,'totalHitsAccuracy':'calculated','results':[scene(3),scene(4)],'nextRecord':5}},
               {'data':{'totalHits':5,'totalHitsAccuracy':'calculated','results':[scene(5)],'nextRecord':5}}]
        sent=[]
        def post(session,url,data=None,**kwargs):
            response=Mock();response.raise_for_status.return_value=None
            if url.endswith('/scene-search'):
                sent.append(json.loads(data));response.json.return_value=pages[len(sent)-1]
            return response
        with patch.object(requests.Session,'post',post):
            found,stats=usgs_search(ac,'landsat_ot_c2_l1',[17.9,-67.2,18.0,-66.9],'2026-08-01T00:00:00+00:00','2026-08-21T00:00:00+00:00',70,page=2)
        self.assertEqual([f['product'] for f in found],['P1','P2','P3','P4','P5'])
        self.assertEqual([body['startingNumber'] for body in sent],[1,3,5])
        self.assertEqual(sent[0]['sceneFilter']['spatialFilter']['lowerLeft'],{'longitude':-67.2,'latitude':17.9})
        self.assertEqual(sent[0]['sceneFilter']['cloudCoverFilter']['max'],70)
        self.assertEqual((stats['recordsReturned'],stats['pages'],usgs_completeness(stats)),(5,3,'COMPLETE'))
        self.assertEqual(usgs_completeness({'totalHits':1200,'recordsReturned':1000}),'INCOMPLETE')
        self.assertEqual(usgs_completeness({'totalHits':4,'recordsReturned':4,'totalHitsAccuracy':'approximate'}),'UNKNOWN')
        self.assertEqual(usgs_completeness(None),'UNKNOWN')

    def test_earthexplorer_fallback_when_m2m_denied(self):
        from oceanos import native
        ac=self.ac([LANDSAT])
        with patch('oceanos.native.usgs_sizes',return_value=({},'HTTP_403')), \
             patch('oceanos.native.earthexplorer_sizes',return_value=({'LC09ENT0':1_048_796_200},None)):
            result=native.query(ac,'USGS',self.config)
        self.assertEqual((result['sizes'],native.l1_bytes(result['sources'][0])),('EARTHEXPLORER',1_048_796_200))
        with patch('oceanos.native.usgs_sizes',return_value=({},'HTTP_403')), \
             patch('oceanos.native.earthexplorer_sizes',return_value=({},'LOGIN_EARTHEXPLORER')):
            self.assertEqual(native.query(ac,'USGS',self.config)['sizes'],'NO_DISPONIBLE:HTTP_403,LOGIN_EARTHEXPLORER')

    def test_bundle_size_parsed_from_options_page(self):
        from oceanos.native import bundle_size
        html=('<div class="downloadButtons" data-entityId="LC90050482026005LGN00">'
              '<button type="button" class="btn btn-secondary secondaryDownloadButton" data-entityId="LC90050482026005LGN00" '
              'data-productId="5e81" title="Download Product" ><i class="fa fa-download"></i> 1,000.21 MiB</button>'
              '<button type="button" class="btn btn-secondary secondaryDownloadButton" data-entityId="L1_LC09_B1_TIF" '
              'data-productId="2c" title="Download Product/File"><i class="fa fa-download"></i> 74.56 MiB</button></div>')
        self.assertEqual(bundle_size(html,'LC90050482026005LGN00'),int(1000.21*1024**2))
        self.assertIsNone(bundle_size(html,'L1_LC09_B1_TIF'))

    def test_download_options_bundle_size_or_reason(self):
        from oceanos.native import usgs_sizes
        ac=self.ac([])
        ok=Mock();ok.json.return_value={'data':[
            {'entityId':'E1','productName':'Landsat Collection 2 Level-1 Product Bundle','filesize':900,'available':True},
            {'entityId':'E1','productName':'Landsat Collection 2 Level-1 Band File','filesize':50,'available':False}]}
        with patch('requests.post',return_value=ok):
            self.assertEqual(usgs_sizes(ac,'landsat_ot_c2_l1',['E1']),({'E1':900},None))
        denied=Mock();denied.json.return_value={'errorCode':'AUTH_UNAUTHORIZED','errorMessage':'no','data':None}
        with patch('requests.post',return_value=denied):
            self.assertEqual(usgs_sizes(ac,'landsat_ot_c2_l1',['E1']),({},'AUTH_UNAUTHORIZED'))

    def test_search_explanation_is_readable(self):
        import io, contextlib
        from oceanos import cli
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.show_query({'provider':'USGS','count':1,'returned':2,'completeness':'UNKNOWN','sizes':'NO_DISPONIBLE:HTTP_403,LOGIN_EARTHEXPLORER',
                            'provider_counts':None,'excluded_by_profile':[{'product':NEIGHBOR,'reason':'path/row 006/048 fuera'}]})
        text=out.getvalue()
        for expected in ('2 escenas devueltas, 1 cumplen','desconocida','Descartadas por el perfil (1): 1 por path/row 006/048',
                         'USGS no los entregó'):
            self.assertIn(expected,text)


class ParallelTests(unittest.TestCase):
    """Reparto dinámico de CPU/RAM según el equipo, reservas por etapa y lote con varias escenas a la vez."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cat=Catalog(self.temp.name)
        self.config=profile(PROFILE,'sentinel2',start=START,end=END)

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def named(self, date):
        name=SCENE.replace('20260804T150719',date)
        return self.cat.upsert_scene({**source(),'product':name,'identity':scene_identity(name)})

    def test_plan_adapts_to_free_hardware_and_measured_peaks(self):
        import os
        from oceanos.resources import plan, GB
        with patch.dict(os.environ,{'OCEANOS_CPUS':'','OCEANOS_RAM_GB':''}):
            # 20 CPU: se dejan 2 al sistema; 7,5 GB libres menos 1,5 GB de reserva = 6 GB.
            resources=plan(self.cat,self.config,40*GB,cpus=20,memory=8*GB,free=7.5*GB)
            self.assertEqual((resources.cpu_budget,round(resources.memory_budget/GB,2)),(18,6.0))
            # 4 descargas (cuota CDSE) de 0,4 GB y un ACOLITE de 4,8 GB en los 4,4 GB restantes (al menos uno).
            self.assertEqual((resources.workers,resources.threads()),(5,3))
            self.assertEqual(resources.environment()['OPENBLAS_NUM_THREADS'],'3')
            # Equipo grande: 32 CPU (29 usables) y 60 GB libres de 64 (reserva 6,4 GB): 4 descargas + 10 ACOLITE.
            big=plan(self.cat,self.config,100*GB,cpus=32,memory=64*GB,free=60*GB)
            self.assertEqual((big.cpu_budget,round(big.memory_budget/GB,1),big.workers),(29,53.6,14))
            # La misma máquina con la RAM ocupada por otras aplicaciones lanza menos escenas.
            self.assertEqual(plan(self.cat,self.config,100*GB,cpus=32,memory=64*GB,free=10*GB).workers,5)
            # Landsat: tope prudente de 4 descargas en streaming (0,4 GB) y 3 ACOLITE de 6,6 GB en lo que queda.
            landsat=plan(self.cat,{**self.config,'family':'landsat'},100*GB,cpus=20,memory=31*GB,free=28*GB)
            self.assertEqual((round(landsat.memory_budget/GB,1),landsat.workers),(24.9,7))
            self.assertEqual(plan(self.cat,self.config,4*GB,cpus=32,memory=64*GB,free=60*GB).workers,1)
            self.assertEqual(plan(self.cat,self.config,40*GB,workers=5,cpus=20,memory=8*GB,free=7.5*GB).workers,5)
            # Equipo mínimo: 2 CPU sin reserva, al menos una escena.
            small=plan(self.cat,self.config,40*GB,cpus=2,memory=4*GB,free=1*GB)
            self.assertEqual((small.cpu_budget,small.memory_budget,small.workers),(2,0.0,1))
            self.assertFalse(small.warm)
            process=self.cat.start(self.named('20260804T150719'),'DESCARGA',self.config)
            self.cat.finish(process,'OK','TECNICA_OK',metrics=[{'stage':'acquire','seconds':9,'rss_bytes':3*GB,'ok':True}])
            self.assertAlmostEqual(plan(self.cat,self.config,40*GB,cpus=20,memory=8*GB,free=7.5*GB).peaks['acquire']/GB,3.3)

    def test_environment_variables_fix_cpu_and_ram(self):
        import os
        from oceanos.resources import plan, GB
        with patch.dict(os.environ,{'OCEANOS_CPUS':'4','OCEANOS_RAM_GB':'10'}):
            resources=plan(self.cat,self.config,40*GB,cpus=20,memory=64*GB,free=60*GB)
        self.assertEqual((resources.cpu_budget,resources.memory_budget,resources.workers),(4,10*GB,4))
        self.assertIn('fijado con OCEANOS_CPUS/OCEANOS_RAM_GB',resources.describe())
        with patch.dict(os.environ,{'OCEANOS_CPUS':'cero','OCEANOS_RAM_GB':''}), self.assertRaises(ValueError):
            plan(self.cat,self.config,40*GB,cpus=20,memory=64*GB,free=60*GB)

    def test_hardware_reads_cgroup_limits_and_meminfo(self):
        from oceanos.resources import cgroup_limits, meminfo
        root=Path(self.temp.name)/'cgroup';leaf=root/'docker'/'oceanos';leaf.mkdir(parents=True)
        membership=Path(self.temp.name)/'membership';membership.write_text('0::/docker/oceanos\n')
        self.assertEqual(cgroup_limits(root,membership),(None,None))
        (root/'docker'/'cpu.max').write_text('400000 100000\n')
        (root/'docker'/'memory.max').write_text('12000000000\n');(root/'docker'/'memory.current').write_text('1000000000\n')
        (leaf/'memory.max').write_text('8000000000\n');(leaf/'memory.current').write_text('2000000000\n')
        (leaf/'cpu.max').write_text('max 100000\n')
        # El límite más estricto de la jerarquía: 4 CPU del padre y 6 GB libres del propio.
        self.assertEqual(cgroup_limits(root,membership),(4,6_000_000_000))
        info=Path(self.temp.name)/'meminfo';info.write_text('MemTotal: 20000000 kB\nMemFree: 1000 kB\nMemAvailable: 15000000 kB\n')
        self.assertEqual(meminfo(info),(20000000*1024,15000000*1024))

    def test_stages_start_only_if_their_ram_fits(self):
        from oceanos.resources import Resources, PEAKS, GB
        # Picos de una descarga que acumula el archivo en memoria (como la nativa de USGS).
        heavy={'acquire':2.6*GB,'extract':1.2*GB,'process':4.8*GB}
        small=Resources(heavy,cpus=20,memory=8*GB,free=7.5*GB)
        with small.condition:
            self.assertTrue(small.admit('acquire'));self.assertTrue(small.admit('acquire'))
            self.assertFalse(small.admit('acquire'));self.assertEqual(small.blocked['acquire'],'RAM')
            small.free('acquire');small.free('acquire')
            # Primer ACOLITE: solo, mientras prepara LUT; luego ACOLITE (4,8) + descarga (2,6) no caben en 6.
            self.assertTrue(small.admit('process'));self.assertFalse(small.admit('extract'))
            self.assertEqual(small.blocked['extract'],'que ACOLITE prepare sus LUT')
            small.free('process');small.warm=True
            self.assertTrue(small.admit('process'));self.assertFalse(small.admit('acquire'))
            small.free('process')
            # Con ACOLITE esperando no arranca otra descarga, aunque no haya nada en curso.
            small.waiting={'process':1}
            self.assertFalse(small.admit('acquire'));self.assertTrue(small.admit('process'))
            self.assertEqual(small.blocked['acquire'],'que avance una escena más adelantada')
        large=Resources(PEAKS['sentinel2'],cpus=32,memory=64*GB,free=50*GB);large.warm=True
        with large.condition:
            self.assertTrue(all(large.admit('process') for _ in range(9)));self.assertFalse(large.admit('process'))
        # Una etapa sola entra aunque supere la RAM asignada.
        tiny=Resources(PEAKS['landsat'],cpus=2,memory=4*GB)
        with tiny.condition:
            self.assertTrue(tiny.admit('process'))

    def test_downloads_respect_provider_quota(self):
        import os
        from oceanos.resources import Resources, plan, PEAKS, GB
        resources=Resources(PEAKS['sentinel2'],cpus=20,memory=64*GB,free=60*GB,limits={'acquire':4});resources.warm=True
        with resources.condition:
            # CDSE gratuito: 4 descargas a la vez aunque la RAM alcance para más.
            self.assertTrue(all(resources.admit('acquire') for _ in range(4)));self.assertFalse(resources.admit('acquire'))
            self.assertEqual(resources.blocked['acquire'],'turno de descarga (4 a la vez)')
            # Las demás etapas siguen entrando mientras las descargas esperan turno.
            self.assertTrue(resources.admit('process'))
            resources.free('acquire');self.assertTrue(resources.admit('acquire'))
        with patch.dict(os.environ,{'OCEANOS_CPUS':'','OCEANOS_RAM_GB':'','OCEANOS_DESCARGAS':''}):
            sentinel=plan(self.cat,self.config,40*GB,cpus=20,memory=32*GB,free=28*GB)
            self.assertEqual(sentinel.limits,{'acquire':4})
            self.assertIn('descargas a la vez 4',sentinel.describe())
            self.assertEqual(plan(self.cat,{**self.config,'family':'landsat'},40*GB,cpus=20,memory=32*GB,free=28*GB).limits,{'acquire':4})
        with patch.dict(os.environ,{'OCEANOS_DESCARGAS':'2'}):
            self.assertEqual(plan(self.cat,self.config,40*GB,cpus=20,memory=32*GB,free=28*GB).limits,{'acquire':2})
        with patch.dict(os.environ,{'OCEANOS_DESCARGAS':'0'}), self.assertRaises(ValueError):
            plan(self.cat,self.config,40*GB,cpus=20,memory=32*GB,free=28*GB)

    def test_live_free_ram_holds_extra_stages(self):
        from oceanos.resources import Resources, PEAKS, GB
        now={'free':40*GB}
        resources=Resources(PEAKS['sentinel2'],cpus=32,memory=64*GB,free=60*GB,live=lambda:now['free']);resources.warm=True
        with resources.condition:
            self.assertTrue(resources.admit('process'))
            # Otra aplicación ocupó la RAM: 5 GB libres no dan para 4,8 GB más la reserva de 6,4 GB.
            now['free']=5*GB
            self.assertFalse(resources.admit('process'))
            now['free']=20*GB
            self.assertTrue(resources.admit('process'))

    def test_stop_ends_wait_for_ram(self):
        from oceanos.resources import Resources, PEAKS, GB
        resources=Resources(PEAKS['sentinel2'],cpus=4,memory=8*GB)
        with resources.condition:
            resources.admit('process')
        resources.stop.set()
        with self.assertRaises(KeyboardInterrupt):
            with resources.reserve('acquire'):
                pass
        self.assertEqual(resources.waiting['acquire'],0)

    def test_parallel_batch_processes_scenes_at_once(self):
        import threading
        from oceanos.resources import Resources, PEAKS, GB
        ok,bad,third=(self.named(d) for d in ('20260804T150719','20260809T150719','20260811T150719'))
        self.cat.enqueue([ok,bad,third])
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config
        runner.engine={};runner.metrics=[];runner.wait=lambda _:None
        runner.resources=Resources(PEAKS['sentinel2'],cpus=4,memory=16*GB,workers=2)
        together=threading.Barrier(2,timeout=10);threads=set()
        def fake(self,scene,force=False):
            threads.add(threading.get_ident())
            self.current_run=self.catalog.start(scene,'DESCARGA',self.config)
            if scene!=third:
                together.wait()
            if scene==bad:
                self.catalog.finish(self.current_run,'FALLIDO',error='RuntimeError');raise RuntimeError('fallo')
            self.catalog.finish(self.current_run,'OK','TECNICA_OK')
        with patch.object(Pipeline,'run',fake):
            result=runner.batch([ok,bad,third])
        self.assertEqual(len(threads),2)
        self.assertEqual((result['failed'],sorted(result['runs'])),([bad],[1,2,3]))
        self.assertEqual({i['escena']:i['estado'] for i in self.cat.queue()},{ok:'PROCESADA',bad:'FALLIDA',third:'PROCESADA'})

    def test_progress_keeps_one_slot_per_scene(self):
        import io, threading
        from oceanos.progress import Progress
        stream=io.StringIO();bar=Progress(stream,interactive=False,every=0)
        started,finish=threading.Event(),threading.Event()
        def first():
            bar.scene(1,2,'S2B 2026-08-04');bar.download(250_000_000,500_000_000,5_000_000,50)
            started.set();finish.wait(5)
        thread=threading.Thread(target=first);thread.start();started.wait(5)
        bar.scene(2,2,'S2C 2026-08-09');bar.stage('ACOLITE',90,180);bar.message('TECNICA_OK: listo')
        finish.set();thread.join()
        text=stream.getvalue()
        self.assertIn('[1/2] S2B 2026-08-04  descarga',text)
        self.assertIn('[2/2] S2C 2026-08-09  ACOLITE ~50%',text)
        self.assertIn('[2/2] TECNICA_OK: listo',text)

    def test_cleanup_is_hidden_from_help_but_still_works(self):
        from oceanos import cli
        parser=cli.parser()
        self.assertNotIn('cleanup',parser.format_help())
        self.assertIn('recover',parser.format_help())
        self.assertEqual((parser.parse_args(['cleanup','7']).command,parser.parse_args(['cleanup','7']).run),('cleanup',7))

    def test_run_plans_workers_from_option(self):
        import io, contextlib
        from oceanos import cli
        names=[self.named('20260804T150719'),self.named('20260809T150719')]
        pipeline=Mock(last_query=None);pipeline.search.return_value=names;pipeline.used.return_value=0
        pipeline.batch.return_value={'runs':[],'failed':[],'seconds':1}
        out=io.StringIO()
        with patch('oceanos.cli.Pipeline',return_value=pipeline),patch('oceanos.cli.ensure_masks'), \
             patch('oceanos.cli.derived_products'),contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--storage',self.temp.name,'--sensor','sentinel2','--start',START,'--end',END,
                                       'run','--trabajadores','2']),0)
        self.assertEqual(pipeline.resources.workers,2)
        self.assertIn('Paralelo: 2 escena(s) a la vez',out.getvalue())
        err=io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            cli.parser().parse_args(['run','--trabajadores','0'])
        self.assertIn('entero ≥ 1',err.getvalue())



class MockProvider:
    """Servidor HTTP local que imita a CDSE: token, redirección del catálogo a la descarga y archivo."""
    def __init__(self, body=b'x'*3_000_000, status=200, headers=None, location=None):
        import threading
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        self.body, self.hits, self.headers = body, {'token':0,'logout':0,'catalogue':0,'download':0}, []
        provider = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length') or 0))
                kind = 'logout' if self.path.endswith('/logout') else 'token'
                provider.hits[kind] += 1
                payload = json.dumps({'access_token':'acceso','refresh_token':'renovar'}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers()
                self.wfile.write(payload)
            def do_GET(self):
                provider.headers.append(self.headers.get('Authorization'))
                if self.path.startswith('/catalogue'):
                    provider.hits['catalogue'] += 1
                    self.send_response(301);self.send_header('Location',location or f'{provider.base}/download/value')
                    self.send_header('Content-Length','0');self.end_headers();return
                provider.hits['download'] += 1
                self.send_response(status)
                for key, value in (headers or {}).items(): self.send_header(key,value)
                data = provider.body if status==200 else b''
                self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.ac = Mock()
        self.ac.config = {'CDSE_odata':self.base+'/catalogue','CDSE_auth':self.base+'/auth/token'}
        self.ac.shared.auth.return_value = ('usuario','clave')

    def close(self):
        self.server.shutdown();self.server.server_close()


class DownloadTests(unittest.TestCase):
    """Descarga CDSE en streaming, motivos de fallo, reintentos, presupuesto y LUT."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.raw=Path(self.temp.name)/'raw';self.raw.mkdir()
        self.cat=Catalog(Path(self.temp.name)/'storage')
        self.config=profile(PROFILE,'sentinel2',start=START,end=END)

    def tearDown(self):
        self.cat.db.close();self.temp.cleanup()

    def test_cdse_download_streams_once_to_disk_with_hashes(self):
        import hashlib
        from oceanos.native import cdse_download
        provider=MockProvider()
        try:
            path,digests=cdse_download(provider.ac,source(),self.raw)
        finally:
            provider.close()
        # Una sola petición del archivo (ACOLITE hace dos), con el token también tras la redirección.
        self.assertEqual(provider.hits,{'token':1,'logout':1,'catalogue':1,'download':1})
        self.assertEqual(provider.headers,['Bearer acceso','Bearer acceso'])
        self.assertEqual((path.name,path.read_bytes()),(SCENE.split('.')[0]+'.zip',provider.body))
        self.assertEqual(digests,{'md5':hashlib.md5(provider.body).hexdigest(),'sha256':hashlib.sha256(provider.body).hexdigest()})
        self.assertEqual(list(self.raw.glob('*.part')),[])

    def test_cdse_download_reports_quota_and_refuses_foreign_redirects(self):
        from oceanos.native import cdse_download, DownloadError
        provider=MockProvider(status=429,headers={'Retry-After':'240'})
        try:
            with self.assertRaises(DownloadError) as caught: cdse_download(provider.ac,source(),self.raw)
        finally:
            provider.close()
        self.assertEqual((caught.exception.reason,caught.exception.retry_after),('HTTP_429',240))
        self.assertEqual(provider.hits['logout'],1)
        foreign=MockProvider(location='http://otro.example.com/value')
        try:
            with self.assertRaises(DownloadError) as caught: cdse_download(foreign.ac,source(),self.raw)
        finally:
            foreign.close()
        self.assertEqual((caught.exception.reason,foreign.hits['download']),('REDIRECCION_NO_CONFIABLE',0))

    def test_acquire_verifies_with_streamed_hashes_and_usgs_reasons(self):
        import hashlib
        from oceanos.native import acquire, DownloadError
        body=b'contenido';archive=self.raw/'scene.zip';archive.write_bytes(body)
        digests={'md5':hashlib.md5(body).hexdigest(),'sha256':hashlib.sha256(body).hexdigest()}
        data=source(checksum=digests['md5'],metadata={'Checksum':[{'Algorithm':'MD5','Value':digests['md5']}],'ContentLength':len(body)})
        with patch('oceanos.native.cdse_download',return_value=(archive,digests)), patch('oceanos.native.file_hash') as rehash:
            result=acquire(Mock(),data,self.raw)
        rehash.assert_not_called()
        self.assertEqual(result['source']['sha256'],digests['sha256'])
        with patch('oceanos.native.cdse_download',return_value=(archive,{**digests,'md5':'otro'})):
            with self.assertRaises(ValueError): acquire(Mock(),data,self.raw)
        ac=Mock();ac.shared.auth.return_value=None;ac.api.earthexplorer.auth.return_value=None
        with self.assertRaises(DownloadError) as caught:
            acquire(ac,{'provider':'USGS','id':'e','dataset':'d','product':'p'},self.raw)
        self.assertEqual(caught.exception.reason,'SIN_CREDENCIALES')
        ac.api.earthexplorer.download.assert_not_called()

    def test_retry_policy_depends_on_failure_reason(self):
        from oceanos.pipeline import StageError
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config;runner.progress=None
        runner.resources=None;waits=[];runner.wait=waits.append
        process=self.cat.start(self.cat.upsert_scene(source()),'DESCARGA',self.config)
        def failing(code,retry_after=None):
            calls=[]
            def function():
                calls.append(1);raise StageError('acquire',code,retry_after)
            return function,calls
        with patch('builtins.print'):
            function,calls=failing('HTTP_401')
            with self.assertRaises(StageError): runner.retry(function,process)
            self.assertEqual((len(calls),waits),(1,[]))
            # 429 con Retry-After corto: se espera lo pedido (mín. 30 s); largo: no se espera, queda FALLIDA.
            function,calls=failing('HTTP_429',45)
            with self.assertRaises(StageError): runner.retry(function,process)
            self.assertEqual((len(calls),waits),(3,[45,45]))
            waits.clear();function,calls=failing('HTTP_429',500)
            with self.assertRaises(StageError): runner.retry(function,process)
            self.assertEqual((len(calls),waits),(1,[]))
            function,calls=failing('CONEXION')
            with self.assertRaises(StageError): runner.retry(function,process)
            self.assertEqual(waits,[10,30])
        messages=[r['mensaje'] for r in self.cat.db.execute("SELECT mensaje FROM eventos WHERE tipo='INTENTO_FALLIDO' ORDER BY id")]
        self.assertEqual(messages[0],'Descarga, intento 1 de 3: credenciales rechazadas (401) (no se reintenta)')
        self.assertIn('cuota del proveedor superada (429)',messages[1])
        self.assertTrue(any(m.endswith('(429) (no se reintenta)') for m in messages))
        self.assertEqual(messages[-1],'Descarga, intento 3 de 3: conexión cortada')

    def test_download_progress_reads_partial_file(self):
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.progress=Mock()
        (self.raw/'scene.zip.part').write_bytes(b'x'*1000)
        runner.watch('acquire',os.getpid(),self.temp.name,time.monotonic(),
                     {'source':source(metadata={'ContentLength':4000}),'raw':str(self.raw)},{})
        done,total=runner.progress.download.call_args.args[:2]
        self.assertEqual((done,total),(1000,4000))
        # Antes del .part se miden los bytes del proceso (token, KB); al aparecer el .part la velocidad no es negativa.
        state={'measure':'proceso','first':(time.monotonic()-5,3000)}
        runner.watch('acquire',os.getpid(),self.temp.name,time.monotonic(),
                     {'source':source(metadata={'ContentLength':4000}),'raw':str(self.raw)},state)
        rate=runner.progress.download.call_args.args[2]
        self.assertTrue(rate is None or rate >= 0)
        self.assertEqual(state['measure'],'part')

    def test_budgets_for_temporaries_and_superimagen(self):
        from oceanos.pipeline import DISK_MARGIN, StageError, superimagen_bytes
        storage=self.cat.storage
        (storage/'superimagen'/'escenas').mkdir(parents=True);(storage/'superimagen'/'escenas'/'b.tif').write_bytes(b'x'*5000)
        temp=storage/'temporary'/'9';temp.mkdir(parents=True);(temp/'raw.zip').write_bytes(b'x'*700)
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.roots=[storage/'temporary'];runner.config={'budget':10**9}
        self.assertEqual((runner.used(),superimagen_bytes(storage)),(700,5000))
        runner.check_disk()
        with patch('oceanos.pipeline.disk_free',return_value=DISK_MARGIN-1):
            with self.assertRaises(RuntimeError) as caught: runner.check_disk()
        self.assertEqual(str(caught.exception),'Disco casi lleno')
        runner.config={'budget':500}
        with self.assertRaises(RuntimeError): runner.check_disk()
        # La superimagen tiene su propio presupuesto: con lo medido por escena, no se exporta si no cabe.
        runner.config={**self.config,'superimagen_budget':6000}
        self.cat.record_product(self.cat.upsert_scene(source()),'ponce_guayanilla','water2coast_v1',estado='OK',sensor='S2',bytes=900)
        runner.check_superimagen_budget()
        runner.config['superimagen_budget']=5500
        with self.assertRaises(StageError) as caught: runner.check_superimagen_budget()
        self.assertEqual(caught.exception.reason,'PRESUPUESTO_SUPERIMAGEN')

    def test_first_acolite_runs_alone_only_without_luts(self):
        from oceanos.resources import luts_ready
        acolite=Path(self.temp.name)/'acolite'
        self.assertFalse(luts_ready(acolite,['S2A','S2C']))
        for family in ('ACOLITE-LUT-202110','RSKY-202102'):
            for sensor in ('S2A_MSI','S2C_MSI_V4'):
                folder=acolite/'data'/'LUT'/family/sensor;folder.mkdir(parents=True);(folder/'lut.nc').touch()
        (acolite/'data'/'LUT'/'Gas').mkdir();(acolite/'data'/'LUT'/'Gas'/'gas.nc').touch()
        self.assertTrue(luts_ready(acolite,['S2A','S2C']))
        self.assertFalse(luts_ready(acolite,['S2A','S2B']))


class RangeProvider:
    """Servidor HTTP local para `fetch`: corta la primera respuesta y atiende Range/If-Range con ETag."""
    def __init__(self, body=b'abcdefghij'*300_000, cut=2_500_000, etag='"v1"', honor_range=True):
        import threading
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        self.body, self.cut, self.etag, self.requests = body, cut, etag, []
        provider = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args): pass
            def do_GET(self):
                wanted, condition = self.headers.get('Range'), self.headers.get('If-Range')
                provider.requests.append((wanted, condition))
                start = int(wanted.split('=')[1].rstrip('-')) if wanted else 0
                partial = wanted and honor_range and condition == provider.etag
                data = provider.body[start:] if partial else provider.body
                self.send_response(206 if partial else 200)
                self.send_header('ETag', provider.etag);self.send_header('Content-Length', str(len(data)))
                if partial:
                    self.send_header('Content-Range', f'bytes {start}-{len(provider.body)-1}/{len(provider.body)}')
                self.end_headers()
                if provider.cut is not None:
                    # Primera respuesta: se corta la conexión a mitad del archivo.
                    self.wfile.write(data[:provider.cut]);provider.cut=None;self.wfile.flush()
                    self.close_connection = True;return
                self.wfile.write(data)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}/file'
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown();self.server.server_close()


class NoRepeatTests(unittest.TestCase):
    """Cola sin descargas repetidas, reanudación de descargas, descarga Landsat propia y auxiliares por día."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cat=Catalog(Path(self.temp.name)/'storage')
        self.config=profile(PROFILE,'sentinel2',start=START,end=END)
        self.imports=self.cat.storage/'importados';self.imports.mkdir()
        self.raw=Path(self.temp.name)/'raw';self.raw.mkdir()

    def tearDown(self):
        self.cat.db.close();self.temp.cleanup()

    def version(self, generated, date='20260804T150719', baseline='N0512'):
        name=SCENE.replace('20260804T150719',date).replace('20260804T182348',generated).replace('N0512',baseline)
        name=self.cat.upsert_scene({**source(),'product':name,'identity':scene_identity(name)})
        self.cat.set_zones(name,['la_parguera_guanica','ponce_guayanilla'])
        return name

    def runner(self):
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config;runner.engine={}
        runner.acolite=ACOLITE;runner.roots=[];runner.wait=lambda _:None;runner.metrics=[]
        runner.progress=None;runner.resources=None
        return runner

    def finish_zones(self, scene, state='OK'):
        for zone in ('la_parguera_guanica','ponce_guayanilla'):
            self.cat.record_product(scene,zone,'water2coast_v1',estado=state,sensor='S2',fecha='2026-08-04')

    def test_queue_takes_one_version_per_acquisition_and_skips_completed(self):
        old=self.version('20260804T182348');new=self.version('20260901T101010',baseline='N0600')
        other=self.version('20260809T182348',date='20260809T150719')
        queued,skipped=self.cat.enqueue([old,new,other])
        # Reproceso del proveedor: misma adquisición, entra solo la versión más reciente.
        self.assertEqual((sorted(queued),list(skipped)),(sorted([new,other]),[old]))
        self.assertIn(new,skipped[old])
        # Un registro posterior no duplica la adquisición que ya está en la cola.
        self.assertEqual(self.cat.enqueue([old])[0],[])
        # Con todas sus zonas terminadas (aunque sea en otra versión), la adquisición no vuelve a la cola.
        self.cat.dequeue(new);self.finish_zones(old,'NUBOSA')
        queued,skipped=self.cat.enqueue([old,new],self.cat.completed('water2coast_v1'))
        self.assertEqual(queued,[])
        self.assertEqual(set(skipped.values()),{'su adquisición ya está procesada en todas sus zonas'})

    def test_pending_defers_repeated_acquisition(self):
        old=self.version('20260804T182348');new=self.version('20260901T101010',baseline='N0600')
        self.cat.scene_state(old,'FALLIDA');self.cat.scene_state(new,'PENDIENTE')
        ready,_,_,deferred=self.cat.pending(self.config)
        self.assertEqual((ready,deferred),([new],[old]))

    def test_run_does_not_download_an_acquisition_with_all_zones_done(self):
        scene=self.version('20260804T182348');self.cat.enqueue([scene])
        self.finish_zones(scene)
        runner=self.runner();calls=[]
        runner.call=lambda operation,**args: calls.append(operation) or (_ for _ in ()).throw(RuntimeError('red'))
        with patch('builtins.print'):
            result=runner.batch([scene])
        processes=self.cat.db.execute('SELECT count(*) FROM procesos').fetchone()[0]
        self.assertEqual((calls,processes,result['runs'],result['failed']),([],0,[],[]))
        self.assertEqual(self.cat.db.execute('SELECT estado FROM escenas WHERE escena=?',(scene,)).fetchone()[0],'DISPONIBLE')
        self.assertEqual(list(self.cat.storage.glob('temporary/*')),[])
        # Con --force sí se intenta (aquí la red falla a propósito).
        with patch('builtins.print'), patch.object(Pipeline,'check_superimagen_budget'), self.assertRaises(Exception):
            runner.run(scene,force=True)
        self.assertEqual(calls[0],'acquire')

    def test_fetch_resumes_cut_download_with_range(self):
        import hashlib, requests
        from oceanos.native import fetch, DownloadError
        provider=RangeProvider();target=self.raw/'scene.zip'
        try:
            with requests.Session() as session:
                with self.assertRaises(DownloadError) as caught: fetch(session,provider.url,target,'127.0.0.1')
                self.assertEqual(caught.exception.reason,'CONEXION')
                # Se conservan los bloques completos (1 MiB) recibidos antes del corte.
                part=target.with_name('scene.zip.part');kept=part.stat().st_size
                self.assertEqual(kept,2*1024*1024)
                digests=fetch(session,provider.url,target,'127.0.0.1')
        finally:
            provider.close()
        # El segundo intento pide solo lo que falta, condicionado a que el archivo no haya cambiado.
        self.assertEqual(provider.requests,[(None,None),(f'bytes={kept}-','"v1"')])
        self.assertEqual(target.read_bytes(),provider.body)
        self.assertEqual(digests,{'md5':hashlib.md5(provider.body).hexdigest(),'sha256':hashlib.sha256(provider.body).hexdigest()})
        self.assertEqual(sorted(p.name for p in self.raw.iterdir()),['scene.zip'])

    def test_fetch_restarts_when_file_changed_or_range_ignored(self):
        import requests
        from oceanos.native import fetch, DownloadError
        for change in ('etag','ignore'):
            provider=RangeProvider(honor_range=change!='ignore');target=self.raw/f'{change}.zip'
            try:
                with requests.Session() as session:
                    with self.assertRaises(DownloadError): fetch(session,provider.url,target,'127.0.0.1')
                    if change=='etag':
                        provider.etag='"v2"';provider.body=b'z'*2_600_000
                    fetch(session,provider.url,target,'127.0.0.1')
            finally:
                provider.close()
            # El servidor manda el archivo entero (200) y se escribe desde cero, sin mezclar pedazos.
            self.assertEqual(target.read_bytes(),provider.body)

    def usgs_server(self, m2m):
        """Servidor local que imita M2M (si `m2m`) y EarthExplorer; devuelve (ac, hits, body, cerrar)."""
        import threading
        from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
        body=b't'*2_500_000;hits=[]
        button=('<button class="btn btn-secondary secondaryDownloadButton" title="Download Product" '
                'data-entityId="LC90050482026217LGN00" data-productId="5e81f14f92acf9ef">Product Bundle 2.38 MiB</button>')
        options=[{'entityId':'LC90050482026217LGN00','id':'p1','available':True,
                  'productName':'Landsat Collection 2 Level-1 Product Bundle'}]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def reply(self, data, kind='text/html'):
                self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
                self.end_headers();self.wfile.write(data)
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length') or 0));hits.append(self.path)
                if not self.path.startswith('/api/') or not m2m:
                    return self.reply(b'ok')
                data={'download-options':options,'download-request':{'availableDownloads':[{'url':base+'/bundle'}]}}
                self.reply(json.dumps({'data':data.get(self.path.rsplit('/',1)[1])}).encode(),'application/json')
            def do_GET(self):
                hits.append(self.path)
                if self.path=='/ers/login': self.reply(b'<input name="csrf" value="c1">')
                elif self.path.startswith('/download/options/'): self.reply(button.encode())
                elif self.path.endswith('/EE/'): self.reply(json.dumps({'url':base+'/bundle'}).encode(),'application/json')
                else: self.reply(body,'application/x-tar')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);base=f'http://127.0.0.1:{server.server_address[1]}'
        threading.Thread(target=server.serve_forever,daemon=True).start()
        ac=Mock();ac.config={'EARTHEXPLORER_ers':base+'/ers','EARTHEXPLORER_download':base+'/download',
                             'EARTHEXPLORER_api':base+'/api'}
        ac.shared.auth.return_value=('usuario','clave');ac.api.earthexplorer.auth.return_value='token'
        return ac,hits,body,lambda: (server.shutdown(),server.server_close())

    def test_usgs_download_uses_m2m_download_request(self):
        import hashlib
        from oceanos.native import usgs_download
        ac,hits,body,close=self.usgs_server(m2m=True)
        data={'provider':'USGS','id':'LC90050482026217LGN00','dataset':'landsat_ot_c2_l1','product':'LC09_L1TP_005048_20260805_20260806_02_T1'}
        try:
            with patch('oceanos.native.USGS_DOMAIN','127.0.0.1'):
                path,digests,route=usgs_download(ac,data,self.raw)
        finally:
            close()
        self.assertEqual((route,path.read_bytes(),digests['sha256']),('M2M',body,hashlib.sha256(body).hexdigest()))
        self.assertEqual([h for h in hits if h.startswith('/api/')],
                         ['/api/download-options','/api/download-request','/api/download-order-remove','/api/logout'])
        self.assertNotIn('/ers/login',hits)

    def test_usgs_download_falls_back_to_earthexplorer(self):
        import hashlib
        from oceanos.native import usgs_download, bundle_ids
        ac,hits,body,close=self.usgs_server(m2m=False)
        data={'provider':'USGS','id':'LC90050482026217LGN00','dataset':'landsat_ot_c2_l1','product':'LC09_L1TP_005048_20260805_20260806_02_T1'}
        try:
            with patch('oceanos.native.USGS_DOMAIN','127.0.0.1'):
                path,digests,route=usgs_download(ac,data,self.raw)
        finally:
            close()
        self.assertEqual((route,path.name,path.read_bytes()),('EARTHEXPLORER',data['product']+'.tar',body))
        self.assertEqual(digests['sha256'],hashlib.sha256(body).hexdigest())
        # Una sola transferencia del bundle (la nativa pide dos) y cierre de sesión EROS.
        self.assertEqual(hits.count('/bundle'),1)
        self.assertIn('/download/5e81f14f92acf9ef/LC90050482026217LGN00/EE/',hits);self.assertEqual(hits[-1],'/ers/logout')
        ac.api.earthexplorer.download.assert_not_called()
        self.assertIsNone(bundle_ids('<button data-entityId="X" data-productId="1">','OTRA'))
        # Una URL de descarga fuera de USGS no se sigue.
        from oceanos.native import trusted_host
        self.assertFalse(trusted_host('https://evilusgs.gov/x','usgs.gov'))
        self.assertTrue(trusted_host('https://landsatlook.usgs.gov/x','usgs.gov'))

    def test_report_lists_successes_and_failures_with_reason(self):
        import io, contextlib, csv
        from oceanos import cli
        ok=self.version('20260804T182348');bad=self.version('20260809T182348',date='20260809T150719')
        self.cat.enqueue([ok,bad])
        first=self.cat.start(ok,'DESCARGA',self.config);self.cat.finish(first,'OK','TECNICA_OK')
        self.cat.record_product(ok,'ponce_guayanilla','water2coast_v1',proceso=first,estado='OK')
        self.cat.record_product(ok,'la_parguera_guanica','water2coast_v1',proceso=first,estado='NUBOSA')
        self.cat.scene_state(ok,'PROCESADA')
        second=self.cat.start(bad,'DESCARGA',self.config);self.cat.downloaded(second,None,None,3)
        self.cat.finish(second,'FALLIDO',error='HTTP_429');self.cat.scene_state(bad,'FALLIDA')
        out=io.StringIO();path=Path(self.temp.name)/'reporte.csv'
        with contextlib.redirect_stdout(out):
            cli.show_report(self.cat,csv_path=path)
        text=out.getvalue()
        self.assertIn('cuota del proveedor superada (429)',text);self.assertIn('OK: 1 · FALLIDA: 1',text)
        rows=list(csv.DictReader(path.open(encoding='utf-8')))
        self.assertEqual([(r['RESULTADO'],r['INTENTOS']) for r in rows],[('OK',''),('FALLIDA','3')])
        self.assertEqual(sorted(rows[0]['ZONAS'].split()),['la_parguera_guanica:NUBOSA','ponce_guayanilla:OK'])
        with contextlib.redirect_stdout(io.StringIO()) as only:
            cli.show_report(self.cat,'FALLIDA')
        self.assertNotIn(ok,only.getvalue())

    def test_two_acolite_of_the_same_day_do_not_run_together(self):
        from oceanos.resources import Resources, PEAKS, GB
        resources=Resources(PEAKS['sentinel2'],cpus=20,memory=64*GB,free=60*GB);resources.warm=True
        with resources.condition:
            self.assertTrue(resources.admit('process','20260804'))
            self.assertFalse(resources.admit('process','20260804'))
            self.assertIn('mismo día',resources.blocked['process'])
            self.assertTrue(resources.admit('process','20260809'))
            resources.free('process','20260804')
            self.assertTrue(resources.admit('process','20260804'))


if __name__=='__main__': unittest.main()
