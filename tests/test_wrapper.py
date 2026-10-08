"""Pruebas de comportamiento del catálogo y del wrapper; no duplican ciencia ACOLITE."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from oceanos.catalog import Catalog
from oceanos.config import ROOT, ACOLITE, profile, exclusive
from oceanos.native import scene_identity, eligible, query, extract
from oceanos.pipeline import Pipeline, cleanup, recover

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
        self.config=profile(ROOT/'config/aoi/lapargera_v1/project.yaml',start=START,end=END)

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def scene(self, data=None):
        return self.cat.upsert_scene(data or source())

    def files(self, process, kinds=('L1R','L2W')):
        folder=self.cat.storage/self.cat.process(process)['carpeta'];folder.mkdir(parents=True,exist_ok=True)
        for kind in kinds:
            path=folder/(kind+'.nc');path.write_bytes(kind.encode());self.cat.artifact(process,kind,path)
        return folder

    def test_status_lists_processes_filters_and_detail(self):
        name=self.scene()
        first=self.cat.start(name,'DESCARGA',self.config);self.cat.finish(first,'FALLIDO',error='TimeoutError')
        second=self.cat.start(name,'DESCARGA',self.config);self.files(second,('L2W',))
        self.cat.finish(second,'OK','TECNICA_OK',metrics=[{'stage':'process','seconds':1,'ok':True}])
        self.assertEqual((first,second),(1,2))
        self.assertEqual(self.cat.process(second)['carpeta'],'runs/0002_S2B_2026-08-04')
        rows=self.cat.runs()
        self.assertEqual([r['id'] for r in rows],[1,2])
        self.assertEqual((rows[1]['satelite'],rows[1]['l2w']),('S2B','runs/0002_S2B_2026-08-04/L2W.nc'))
        self.assertEqual([(r['id'],r['error']) for r in self.cat.runs('FALLIDO')],[(1,'TimeoutError')])
        self.assertEqual([r['id'] for r in self.cat.runs(last=1)],[2])
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

    def test_administrative_metadata_keeps_processing_key(self):
        runner=object.__new__(Pipeline);runner.config=self.config;runner.engine={'revision':'test'}
        a=source(sha256='abc');b=source(sha256='abc');b['metadata']['PublicationDate']='later'
        self.assertEqual(runner.keys(a),runner.keys(b))
        b['sha256']='different'
        self.assertNotEqual(runner.keys(a),runner.keys(b))

    def test_new_products_keep_correction_key(self):
        runner=object.__new__(Pipeline);runner.config=self.config;runner.engine={}
        old=runner.keys(source(sha256='abc'))
        runner.config={**self.config,'products':['fai'],'native':{**self.config['native'],'l2w_parameters':'fai'}}
        new=runner.keys(source(sha256='abc'))
        self.assertEqual(old[1],new[1]);self.assertNotEqual(old[0],new[0])

    def test_missing_or_changed_artifact_does_not_skip(self):
        process=self.cat.start(self.scene(),'DESCARGA',self.config,'work','correction')
        folder=self.files(process,('L2W',))
        self.cat.finish(process,'OK','TECNICA_OK')
        self.assertEqual(self.cat.reusable('work')['proceso'],process)
        (folder/'L2W.nc').write_bytes(b'modified')
        self.assertIsNone(self.cat.reusable('work'))
        self.assertEqual(self.cat.process(process)['archivos'],'FALTAN')

    def raw(self, process):
        raw=self.cat.storage/'temporary'/str(process);raw.mkdir(parents=True);(raw/'partial.zip').touch()
        return raw

    def test_interruption_retains_sources_until_cleanup(self):
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        raw=self.raw(process)
        work=self.cat.storage/self.cat.process(process)['carpeta'];work.mkdir(parents=True);(work/'partial_L1R.nc').touch()
        self.assertEqual(cleanup(self.cat,process),'APLAZADA')
        self.assertTrue((raw/'partial.zip').exists())
        self.assertEqual(self.cat.recover(),1)
        self.assertTrue((raw/'partial.zip').exists())
        self.assertEqual(cleanup(self.cat,process),'HECHA')
        self.assertFalse(raw.exists());self.assertFalse(work.exists())
        self.assertEqual(self.cat.process(process)['estado'],'INTERRUMPIDO')

    def test_interrupted_cleanup_keeps_registered_artifacts(self):
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        folder=self.files(process,('L1R',));raw=self.raw(process)
        self.cat.recover()
        self.assertEqual(cleanup(self.cat,process),'HECHA')
        self.assertFalse(raw.exists());self.assertTrue((folder/'L1R.nc').exists())

    def interrupted(self, state=None):
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        raw=self.raw(process)
        if state: self.cat.finish(process,state)
        return process,raw

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
        escape,_=self.interrupted()
        self.cat.update(escape,carpeta='../outside')
        with patch('oceanos.pipeline.shutil.rmtree',side_effect=OSError):
            result=recover(self.cat)
        self.assertEqual(sorted(result['limpieza_fallida']),[locked,escape])
        for process in (locked,escape):
            self.assertEqual(self.cat.process(process)['limpieza'],'FALLIDA')
        self.assertTrue(locked_raw.exists())
        self.assertEqual(recover(self.cat)['limpiados'],[locked])
        self.assertFalse(locked_raw.exists())

    def test_cleanup_rejects_escape_and_preserves_success(self):
        process,_=self.interrupted('INTERRUMPIDO')
        self.cat.update(process,carpeta='../outside')
        with self.assertRaises(ValueError): cleanup(self.cat,process)
        ok=self.cat.start(self.scene(),'DESCARGA',self.config);self.files(ok)
        self.cat.finish(ok,'OK','TECNICA_OK')
        self.assertEqual(cleanup(self.cat,ok),'HECHA')
        self.assertEqual(self.cat.process(ok)['estado'],'OK')

    def test_cleanup_failure_does_not_repeat_processing(self):
        process=self.cat.start(self.scene(),'DESCARGA',self.config)
        self.raw(process);self.files(process)
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

    def test_l1r_reuse_before_download(self):
        # Un L1R validado y checksum comparable basta: la red no debe llamarse.
        data=source(sha256='local-sha');name=self.scene(data)
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config;runner.engine={}
        runner.acolite=ACOLITE;runner.roots=[];runner.wait=lambda _:None;runner.metrics=[]
        _,correction=runner.keys(data)
        parent=self.cat.start(name,'DESCARGA',self.config,'old-products',correction)
        l1r=self.files(parent,('L1R',))/'L1R.nc'
        self.cat.finish(parent,'OK','TECNICA_OK')
        calls=[]
        def fake(operation,**args):
            calls.append(operation)
            self.assertTrue(args['derive'])
            out=Path(args['output']);result=out/'new_L2W.nc';result.write_bytes(b'L2W')
            intermediate=out/'transient_L2R.nc';intermediate.write_bytes(b'L2R')
            return {'files':{'l1r':str(l1r),'l2r':str(intermediate),'l2w':str(result)},'science_metadata':{},'settings':{},'environment':{}}
        runner.call=fake
        report={'variables':{'l1r':[],'l2r':[],'l2w':[]},'grid':{},'technical':'PASSED','scientific':'PENDING'}
        with patch('oceanos.pipeline.validate',return_value=report):
            process=runner.run(name)
        row=self.cat.process(process)
        self.assertEqual(calls,['process'])
        self.assertEqual((row['tipo'],row['l1r_padre'],row['l1r'],row['estado']),('DERIVADO',parent,None,'OK'))
        folder=self.cat.storage/row['carpeta']
        self.assertEqual(sorted(p.name for p in folder.iterdir()),['new_L2W.nc'])

    def test_failed_recoverable_source_is_cleaned_after_retries(self):
        process,raw=self.interrupted()
        for attempt in range(3): self.cat.event('INTENTO_FALLIDO',f'intento {attempt+1}',process)
        self.cat.finish(process,'FALLIDO')
        self.assertEqual(cleanup(self.cat,process),'HECHA')
        self.assertFalse(raw.exists())
        self.assertEqual(self.cat.process(process)['estado'],'FALLIDO')

    def test_old_catalog_is_backed_up_and_views_work(self):
        import sqlite3
        folder=Path(self.temp.name)/'old';(folder/'catalog').mkdir(parents=True)
        db=sqlite3.connect(folder/'catalog/catalog.sqlite')
        db.execute('CREATE TABLE ejecuciones(id TEXT)');db.execute('PRAGMA user_version=3');db.commit();db.close()
        cat=Catalog(folder)
        self.assertTrue(cat.backup.name.startswith('catalog_v3_respaldo_') and cat.backup.exists())
        tables={r[0] for r in cat.db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        self.assertEqual(tables,{'escenas','procesos','busquedas','eventos','v_resumen','v_cola','v_descargas','v_fallidas','v_disco'})
        for view in ('v_resumen','v_cola','v_descargas','v_fallidas','v_disco'):
            cat.db.execute(f'SELECT * FROM {view}').fetchall()
        self.assertEqual(cat.db.execute('PRAGMA user_version').fetchone()[0],4)
        cat.db.close()
        self.assertIsNone(Catalog(folder).backup)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.config=profile(ROOT/'config/aoi/lapargera_v1/project.yaml',start=START,end=END)

    def test_date_boundaries(self):
        def dated(date):
            return source(identity={**scene_identity(SCENE),'date':date})
        self.assertTrue(eligible(dated('20260801T000000'),self.config))
        self.assertFalse(eligible(dated('20260821T000000'),self.config))
        self.assertFalse(eligible(dated('20260731T235959'),self.config))

    def test_unsupported_product_rejected_before_network(self):
        with self.assertRaises(ValueError): profile(ROOT/'config/aoi/lapargera_v1/project.yaml',['chl_oc4'])
        with self.assertRaises(ValueError): profile(ROOT/'config/aoi/lapargera_v1/landsat.yaml',['ndci'])
        self.assertIsNone(self.config['cloud'])

    def test_products_have_single_source(self):
        self.assertEqual(self.config['native']['l2w_parameters'],'Rrs_*,tur_nechad2009,chl_oc3,ndci,fai,ndvi')
        override=profile(ROOT/'config/aoi/lapargera_v1/project.yaml',[' fai','ndvi','fai'])
        self.assertEqual(override['native']['l2w_parameters'],'fai,ndvi')
        self.assertEqual(override['products'],['fai','ndvi'])
        with self.assertRaises(ValueError): profile(ROOT/'config/aoi/lapargera_v1/project.yaml',['fai',''])

    def test_native_settings_derived_from_yaml(self):
        native=self.config['native']
        self.assertEqual(native['region_name'],'lapargera_v1')
        self.assertEqual(native['limit'],'17.83506768071816,-67.09176880642183,18.047432637275,-66.40241185767644')
        self.assertNotIn('output_projection',native)
        landsat=profile(ROOT/'config/aoi/lapargera_v1/landsat.yaml')['native']
        self.assertEqual(landsat['limit'],native['limit'])
        self.assertEqual(landsat['output_projection_xrange'],'701980,775330')
        self.assertEqual(landsat['output_projection_yrange'],'1997360,1972960')
        self.assertEqual(landsat['output_projection_resolution'],'10,10')
        self.assertEqual(landsat['dsf_tile_dimensions'],'600,600')
        self.assertEqual(landsat['reproject_before_ac'],'True')

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
            self.assertEqual(waits,[60,300])
            self.assertEqual(cat.db.execute("SELECT count(*) FROM busquedas WHERE estado='FALLIDA'").fetchone()[0],3)
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

    def test_l1r_regeneration_uses_full_native_chain_without_reprojection(self):
        from oceanos.native import process
        with tempfile.TemporaryDirectory() as tmp:
            paths={level:str(Path(tmp)/(level+'.nc')) for level in ('l1r','l2r','l2w')}
            for path in paths.values(): Path(path).touch()
            config=Path(tmp)/'settings.txt';config.write_text('l2w_parameters=fai\n')
            ac=Mock();ac.acolite.settings.read.return_value={'l2w_parameters':['fai']}
            ac.acolite.acolite_run.return_value={0:{k:[v] for k,v in paths.items()}}
            result=process(ac,paths['l1r'],config,Path(tmp)/'out',derive=True)
            self.assertEqual(result,paths)
            settings=ac.acolite.acolite_run.call_args.args[0]
            self.assertFalse(settings['output_projection'])
            self.assertFalse(settings['reproject_before_ac'])
            ac.acolite.acolite_l2w.assert_not_called()


class ValidationTests(unittest.TestCase):
    def setUp(self):
        import netCDF4
        import numpy as np
        from pyproj import CRS
        self.temp=tempfile.TemporaryDirectory()
        self.config={'grid':{'xrange_m':[0,20],'yrange_m':[20,0], 'pixel_size_xy_m':[10,-10]},'epsg':32619,'products':['Rrs_*','chl_oc3']}
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
        report=validate(self.files,self.config)
        self.assertEqual(report['technical'],'PASSED')
        self.assertEqual(report['scientific'],'PENDING')
        self.assertEqual(report['finite_pixels']['chl_oc3']['count'],0)

    def test_shifted_grid_rejected(self):
        import netCDF4
        from oceanos.validation import validate
        with netCDF4.Dataset(self.files['l2w'],'a') as ds: ds['x'][:]=[10,20]
        with self.assertRaises(ValueError): validate(self.files,self.config)

    def test_missing_requested_product_rejected(self):
        from oceanos.validation import validate
        self.config['products'].append('ndci')
        with self.assertRaises(ValueError): validate(self.files,self.config)

    def test_incomplete_rrs_wildcard_rejected(self):
        import netCDF4
        from oceanos.validation import validate
        with netCDF4.Dataset(self.files['l2r'],'a') as ds: ds.createVariable('rhos_560','f4',('y','x'))[:]=0
        with self.assertRaises(ValueError): validate(self.files,self.config)



L2W='S2B_MSI_2026_08_04_15_08_03_T19QGV_lapargera_v1_L2W.nc'
L1R='S2B_MSI_2026_08_04_15_08_03_T19QGV_lapargera_v1_L1R.nc'


class QueueSyncTests(unittest.TestCase):
    """Importación por nombre, cola de search→run, tiempos de descarga y resumen."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cat=Catalog(self.temp.name)
        self.config=profile(ROOT/'config/aoi/lapargera_v1/project.yaml',start=START,end=END)
        self.imports=self.cat.storage/'importados';self.imports.mkdir()

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def scene(self, data=None):
        return self.cat.upsert_scene(data or source())

    def named(self, date):
        name=SCENE.replace('20260804T150719',date)
        return self.scene({**source(),'product':name,'identity':scene_identity(name)})

    def runner(self):
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config
        runner.engine={};runner.metrics=[];runner.wait=lambda _:None
        return runner

    def test_output_name_matches_provider_acquisition(self):
        from oceanos.native import output_identity, acquisition_day
        info=output_identity(L2W)
        self.assertEqual((info['region'],info['level']),('lapargera_v1','L2W'))
        self.assertEqual(info['acquisition_key'],acquisition_day(scene_identity(SCENE)))
        landsat=output_identity('L9_OLI_2026_08_05_14_57_33_004047_L1R.nc')
        self.assertEqual(landsat['acquisition_key'],acquisition_day(scene_identity('LC09_L1TP_004047_20260805_20260806_02_T1')))
        with self.assertRaises(ValueError): output_identity('notas.nc')

    def test_sync_registers_by_name_and_is_idempotent(self):
        from oceanos.sync import sync
        name=self.scene()
        (self.imports/L2W).write_bytes(b'l2w');(self.imports/L1R).write_bytes(b'l1r');(self.imports/'otro.nc').write_bytes(b'x')
        report=sync(self.cat,self.imports)
        self.assertEqual(sorted(i['tipo'] for i in report['importados']),['L1R','L2W'])
        self.assertEqual(report['no_reconocidos'],['importados/otro.nc'])
        process=report['importados'][0]['proceso']
        row=self.cat.process(process)
        self.assertEqual((row['tipo'],row['estado'],row['validacion'],row['escena'],row['carpeta'],row['limpieza']),
                         ('IMPORTADO','IMPORTADO','SIN_VERIFICAR',name,'importados','NO_APLICA'))
        self.assertIsNone(row['l2w_sha256'])
        self.assertEqual(self.cat.db.execute('SELECT estado FROM escenas').fetchone()[0],'IMPORTADA')
        self.assertIn('S2B:20260804:19QGV',self.cat.completed('lapargera_v1'))
        self.assertEqual(self.cat.completed('otra_region'),{})
        again=sync(self.cat,self.imports)
        self.assertEqual((again['importados'],again['ya_registrados']),([],2))
        (self.imports/L2W).unlink()
        self.assertEqual(sync(self.cat,self.imports)['desaparecidos'],['importados/'+L2W])
        self.assertEqual(self.cat.completed('lapargera_v1'),{})
        (self.imports/L2W).write_bytes(b'l2w')
        self.assertEqual(sync(self.cat,self.imports)['reaparecidos'],['proceso 1 (importados)'])
        self.assertEqual(cleanup(self.cat,process),'NO_APLICA')
        self.assertTrue((self.imports/L2W).exists())
        # Importado sin verificar: nunca se reutiliza como salida científica.
        self.assertIsNone(self.cat.reusable(None))

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
        self.assertEqual((self.cat.process(1)['escena'],self.cat.db.execute('SELECT estado FROM escenas').fetchone()[0]),(name,'IMPORTADA'))

    def test_sync_adopts_runs_with_readable_names(self):
        from oceanos.sync import sync
        old=self.cat.storage/'runs'/'0df48287585d47b8aa4643234003e5a0'/'output';old.mkdir(parents=True)
        (old/L2W).write_bytes(b'l2w');(old/L1R).write_bytes(b'l1r')
        report=sync(self.cat,self.cat.storage/'runs',hashed=True)
        row=self.cat.process(1)
        self.assertEqual((row['carpeta'],row['l2w']),('runs/0001_S2B_2026-08-04','runs/0001_S2B_2026-08-04/'+L2W))
        self.assertTrue(row['l2w_sha256'])
        self.assertEqual(sorted(p.name for p in (self.cat.storage/'runs').iterdir()),['0001_S2B_2026-08-04'])
        self.assertEqual(sorted(p.name for p in (self.cat.storage/row['carpeta']).iterdir()),[L1R,L2W])
        self.assertEqual(len(report['importados']),2)
        self.assertEqual(sync(self.cat,self.cat.storage/'runs')['ya_registrados'],2)

    def test_sync_rejects_folders_outside_or_reserved(self):
        from oceanos.sync import sync
        (self.cat.storage/'temporary').mkdir()
        for folder in (self.cat.storage/'temporary',self.cat.storage/'catalog',self.cat.storage,Path(tempfile.gettempdir())):
            with self.assertRaises(ValueError): sync(self.cat,folder)

    def test_queue_pending_skips_available_and_out_of_profile(self):
        from oceanos.sync import sync
        inside=self.scene();later=self.named('20260809T150719');outside=self.named('20260901T150719')
        self.cat.enqueue([inside,later,outside])
        (self.imports/L2W).write_bytes(b'l2w');sync(self.cat,self.imports)
        self.cat.scene_state(inside,'PENDIENTE')
        ready,out,available=self.cat.pending(self.config)
        self.assertEqual((ready,out,available),([later],[outside],[inside]))
        self.assertEqual({i['escena']:i['estado'] for i in self.cat.queue()}[inside],'DISPONIBLE')
        self.cat.scene_state(later,'PROCESADA');self.cat.enqueue([later])
        self.assertEqual({i['escena']:i['estado'] for i in self.cat.queue()}[later],'PROCESADA')
        self.cat.dequeue(outside)
        self.assertNotIn(outside,[i['escena'] for i in self.cat.queue()])
        self.assertEqual(self.cat.pending(self.config,force=True)[2],[])

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

    def test_run_uses_queue_without_searching(self):
        from oceanos import cli
        pipeline=Mock()
        with patch('oceanos.cli.Pipeline',return_value=pipeline),patch('oceanos.cli.profile',return_value=self.config):
            with patch('sys.stdout'):
                self.assertEqual(cli.main(['--storage',self.temp.name,'run']),0)
        pipeline.search.assert_not_called();pipeline.batch.assert_not_called()
        name=self.scene();self.cat.enqueue([name])
        pipeline.batch.return_value={'runs':[],'failed':[],'seconds':1}
        with patch('oceanos.cli.Pipeline',return_value=pipeline),patch('oceanos.cli.profile',return_value=self.config):
            with patch('sys.stdout'):
                self.assertEqual(cli.main(['--storage',self.temp.name,'run']),0)
        pipeline.search.assert_not_called()
        pipeline.batch.assert_called_once_with([name],force=False)

    def test_search_registers_only_when_asked(self):
        from oceanos import cli
        name=self.scene();pipeline=Mock(last_query=None);pipeline.search.return_value=[name]
        for argv,queued in ((['search'],0),(['search','--registrar'],1)):
            with patch('oceanos.cli.Pipeline',return_value=pipeline),patch('oceanos.cli.profile',return_value=self.config):
                with patch('sys.stdout'):
                    self.assertEqual(cli.main(['--storage',self.temp.name]+argv),0)
            self.assertEqual(len(self.cat.queue()),queued)

    def test_search_table_shows_date_size_and_scene(self):
        import io, contextlib
        from oceanos import cli
        name=self.scene(source(metadata={'ContentLength':582984789,'ContentDate':{'Start':'2026-08-04T15:07:19Z'}}))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            rows=cli.show_versions(self.cat,[name],self.config)
        self.assertEqual((rows[0]['fecha_utc'],rows[0]['tamano'],rows[0]['estado']),('2026-08-04 15:07','583.0 MB','NUEVA'))
        self.assertIn(SCENE,out.getvalue())

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
    """--sensor y --satelite en search/run, y ayudas con valores válidos."""
    def test_satellite_filter_restricts_profile_platforms(self):
        config=profile(ROOT/'config/aoi/lapargera_v1/project.yaml',start=START,end=END,satellites=['S2C'])
        self.assertEqual(config['search']['platforms'],['S2C'])
        self.assertFalse(eligible(source(),config))
        with self.assertRaises(ValueError): profile(ROOT/'config/aoi/lapargera_v1/project.yaml',satellites=['L8'])

    def test_landsat_platform_is_checked(self):
        name='LC09_L1TP_005048_20260805_20260806_02_T1'
        data={'provider':'USGS','product':name,'format':'TAR','identity':scene_identity(name),'metadata':{}}
        landsat=ROOT/'config/aoi/lapargera_v1/landsat.yaml'
        self.assertTrue(eligible(data,profile(landsat)))
        self.assertFalse(eligible(data,profile(landsat,satellites=['L8'])))

    def test_sensor_and_satellite_accepted_before_or_after_command(self):
        from oceanos import cli
        for argv in (['--sensor','landsat','--satelite','l9','search'],['search','--sensor','landsat','--satelite','LC09']):
            args=cli.parser().parse_args(argv)
            self.assertEqual((args.sensor,args.satelite),('landsat',['L9']))
            self.assertEqual(cli.load_profile(args)['search']['platforms'],['L9'])
        args=cli.parser().parse_args(['--satelite','S2B','run','--start','2026-08-01','--end','2026-08-15'])
        self.assertEqual((args.satelite,args.start,args.sensor),(['S2B'],'2026-08-01',None))
        self.assertEqual(cli.load_profile(args)['family'],'sentinel2')
        with self.assertRaises(ValueError):
            cli.load_profile(cli.parser().parse_args(['search','--sensor','landsat','--satelite','S2B']))

    def test_invalid_values_are_rejected_with_options(self):
        import io, contextlib
        from oceanos import cli
        for argv,hint in ((['search','--satelite','S2D'],'S2A, S2B, S2C'),(['--start','2026-13-01','search'],'AAAA-MM-DD'),
                          (['--products','chl_oc4','search'],'chl_oc3'),(['search','--sensor','modis'],'sentinel2')):
            err=io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit): cli.parser().parse_args(argv)
            self.assertIn(hint,err.getvalue())


LANDSAT='LC09_L1TP_005048_20260805_20260806_02_T1'
NEIGHBOR='LC08_L1TP_005047_20260813_20260814_02_T1'


class UsgsQueryTests(unittest.TestCase):
    """Información de search para Landsat: tamaño, completitud, descartes y fecha."""
    def setUp(self):
        self.config=profile(ROOT/'config/aoi/lapargera_v1/landsat.yaml')

    def ac(self, names):
        ac=Mock();ac.config={'EARTHEXPLORER_api':'https://m2m.example/api'}
        ac.api.earthexplorer.auth.return_value='token'
        attrs=[{'fieldName':'Start Time','value':'2026-08-05 14:57:33'}]
        ac.api.earthexplorer.query.return_value=([n[:4]+'ENT'+str(i) for i,n in enumerate(names)],names,
                                                 ['landsat_ot_c2_l1']*len(names),[attrs]*len(names))
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
        self.assertIn('path/row 005/047 (perfil 005/048)',reasons[NEIGHBOR])
        self.assertIn('L1TP',reasons['LC09_L1GT_005048_20260805_20260806_02_T2'])
        self.assertEqual(native.scene_date(result['sources'][0]),'2026-08-05 14:57')

    def test_scene_search_counters_are_observed_without_patching_acolite(self):
        import requests
        from oceanos.native import observe_post, usgs_completeness
        response=Mock();response.json.return_value={'data':{'totalHits':4,'recordsReturned':4,'totalHitsAccuracy':'actual','results':[1]}}
        with patch.object(requests.Session,'post',return_value=response) as original:
            with observe_post('scene-search') as seen:
                requests.Session().post('https://m2m.example/api/scene-search')
                requests.Session().post('https://m2m.example/api/scene-metadata')
            self.assertIs(requests.Session.post,original)
        self.assertEqual(seen,[{'totalHits':4,'recordsReturned':4,'totalHitsAccuracy':'actual','numExcluded':None,'nextRecord':None}])
        self.assertEqual(usgs_completeness(seen[0]),'COMPLETE')
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
                            'provider_counts':None,'excluded_by_profile':[{'product':NEIGHBOR,'reason':'path/row 005/047 (perfil 005/048)'}]})
        text=out.getvalue()
        for expected in ('2 escenas devueltas, 1 cumplen','desconocida','Descartadas por el perfil (1)',NEIGHBOR,'rol MACHINE'):
            self.assertIn(expected,text)


if __name__=='__main__': unittest.main()
