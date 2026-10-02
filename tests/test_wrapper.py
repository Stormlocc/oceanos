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


def source(checksum='a', **extra):
    return {'provider':'CDSE','product':SCENE,'format':'SAFE','id':'public-id',
            'identity':scene_identity(SCENE),'metadata':{'Checksum':[{'Algorithm':'MD5','Value':checksum}]},**extra}


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.cat=Catalog(self.temp.name)
        self.config=profile(ROOT/'config/aoi/lapargera_v1/project.yaml')

    def tearDown(self):
        self.cat.db.close()
        self.temp.cleanup()

    def version(self, data=None):
        query=self.cat.query('CDSE',{})
        return query,self.cat.observe(query,data or source())

    def test_status_lists_scene_l2w_filters_and_detail(self):
        _,v=self.version()
        first=self.cat.start(v,self.config,'a','b');self.cat.finish(first,'FAILED',error='TimeoutError')
        second=self.cat.start(v,self.config,'c','d')
        path=self.cat.storage/'out_L2W.nc';path.write_bytes(b'L2W')
        self.cat.artifact(second,'L2W',path,{});self.cat.finish(second,'SUCCEEDED','TECHNICAL_PASSED',summary={'metrics':[{'stage':'process'}]})
        rows=self.cat.runs()
        self.assertEqual([r['id'] for r in rows],[first,second])
        self.assertEqual(rows[1]['escena'],SCENE);self.assertEqual(rows[1]['l2w'],'out_L2W.nc')
        self.assertEqual([r['id'] for r in self.cat.runs('FAILED')],[first])
        self.assertEqual(self.cat.runs('FAILED')[0]['error'],'TimeoutError')
        self.assertEqual([r['id'] for r in self.cat.runs(last=1)],[second])
        detail=self.cat.run_detail(second[:8])
        self.assertEqual(detail['artefactos'][0]['tipo'],'L2W');self.assertEqual(detail['metricas'],[{'stage':'process'}])
        self.assertEqual([e['tipo'] for e in detail['eventos']],['STARTED','SUCCEEDED'])
        self.assertNotIn('configuracion',detail)
        with self.assertRaises(ValueError): self.cat.run_detail('zz')

    def test_repeated_queries_and_duplicate_occurrences(self):
        q,v=self.version()
        self.assertEqual(v,self.cat.observe(q,source()))
        _,v2=self.version()
        self.assertEqual(v,v2)
        self.assertEqual(self.cat.db.execute('SELECT count(*) FROM versiones_producto').fetchone()[0],1)
        self.assertEqual(self.cat.db.execute('SELECT ocurrencias FROM observaciones WHERE consulta_id=?',(q,)).fetchone()[0],2)

    def test_content_change_preserves_history(self):
        _,old=self.version(source(sha256='old'))
        _,new=self.version(source('b',sha256='new'))
        self.assertNotEqual(old,new)
        self.assertEqual(self.cat.source(old)['sha256'],'old')
        self.assertNotIn('sha256',self.cat.verified_source(source('c')))
        self.assertEqual(self.cat.verified_source(source())['sha256'],'old')

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
        _,v=self.version();run=self.cat.start(v,self.config,'work','correction')
        path=self.cat.storage/'output.nc';path.write_bytes(b'original')
        self.cat.artifact(run,'L2W',path,{})
        self.cat.finish(run,'SUCCEEDED','TECHNICAL_PASSED')
        self.assertIsNotNone(self.cat.reusable('work'))
        path.write_bytes(b'modified')
        self.assertIsNone(self.cat.reusable('work'))

    def test_interruption_retains_sources_until_cleanup(self):
        _,v=self.version();run=self.cat.start(v,self.config,'a','b')
        raw=self.cat.storage/'temporary'/run;raw.mkdir(parents=True);(raw/'partial.zip').touch()
        work=self.cat.storage/'runs'/run;work.mkdir(parents=True);(work/'partial_L1R.nc').touch()
        self.cat.event('WORK_DIRECTORY',{'path':'runs/'+run,'temporary':'temporary/'+run},run)
        self.assertEqual(cleanup(self.cat,run),'DEFERRED_VALIDATION')
        self.assertTrue((raw/'partial.zip').exists())
        self.assertEqual(self.cat.recover(),1)
        self.assertTrue((raw/'partial.zip').exists())
        self.assertEqual(cleanup(self.cat,run),'DELETED')
        self.assertFalse(raw.exists());self.assertFalse(work.exists())
        self.assertEqual(self.cat.db.execute('SELECT estado FROM ejecuciones WHERE id=?',(run,)).fetchone()[0],'INTERRUPTED')

    def test_interrupted_cleanup_keeps_registered_artifacts(self):
        _,v=self.version();run=self.cat.start(v,self.config,'a','b')
        work=self.cat.storage/'runs'/run;work.mkdir(parents=True)
        l1r=work/'L1R.nc';l1r.write_bytes(b'l1r');self.cat.artifact(run,'L1R',l1r,{})
        raw=self.cat.storage/'temporary'/run;raw.mkdir(parents=True)
        self.cat.event('WORK_DIRECTORY',{'path':'runs/'+run,'temporary':'temporary/'+run},run)
        self.cat.recover()
        self.assertEqual(cleanup(self.cat,run),'DELETED')
        self.assertFalse(raw.exists());self.assertTrue(l1r.exists())

    def interrupted_run(self, state=None):
        _,v=self.version();run=self.cat.start(v,self.config,'a','b')
        raw=self.cat.storage/'temporary'/run;raw.mkdir(parents=True);(raw/'partial.zip').touch()
        self.cat.event('WORK_DIRECTORY',{'path':'runs/'+run,'temporary':'temporary/'+run},run)
        if state: self.cat.finish(run,state)
        return run,raw

    def test_recover_cleans_hard_stop_and_ctrl_c(self):
        hard,hard_raw=self.interrupted_run()
        ctrl_c,ctrl_raw=self.interrupted_run('INTERRUPTED')
        _,failed_raw=self.interrupted_run('FAILED')
        result=recover(self.cat)
        self.assertEqual(result['interrumpidas'],1)
        self.assertEqual(sorted(result['limpiadas']),sorted([hard,ctrl_c]))
        self.assertFalse(hard_raw.exists());self.assertFalse(ctrl_raw.exists())
        self.assertTrue(failed_raw.exists())
        self.assertEqual(recover(self.cat),{'interrumpidas':0,'limpiadas':[],'limpieza_fallida':[]})

    def test_recover_continues_when_cleanup_fails(self):
        locked,locked_raw=self.interrupted_run()
        escape,_=self.interrupted_run()
        self.cat.event('WORK_DIRECTORY',{'temporary':'../outside'},escape)
        with patch('oceanos.pipeline.shutil.rmtree',side_effect=OSError):
            result=recover(self.cat)
        self.assertEqual(sorted(result['limpieza_fallida']),sorted([locked,escape]))
        for run in (locked,escape):
            self.assertEqual(self.cat.db.execute('SELECT limpieza FROM ejecuciones WHERE id=?',(run,)).fetchone()[0],'FAILED')
        self.assertTrue(locked_raw.exists())
        self.assertEqual(recover(self.cat)['limpiadas'],[locked])
        self.assertFalse(locked_raw.exists())

    def test_cleanup_rejects_escape_and_preserves_success(self):
        _,v=self.version();run=self.cat.start(v,self.config,'a','b')
        for kind in ('L1R','L2W'):
            artifact_path=self.cat.storage/(run+'_'+kind+'.nc');artifact_path.write_bytes(kind.encode())
            self.cat.artifact(run,kind,artifact_path,{})
        self.cat.finish(run,'SUCCEEDED','TECHNICAL_PASSED')
        self.cat.event('WORK_DIRECTORY',{'temporary':'../outside'},run)
        with self.assertRaises(ValueError): cleanup(self.cat,run)
        self.assertEqual(self.cat.db.execute('SELECT estado FROM ejecuciones WHERE id=?',(run,)).fetchone()[0],'SUCCEEDED')

    def test_cleanup_failure_does_not_repeat_processing(self):
        _,v=self.version();run=self.cat.start(v,self.config,'a','b')
        raw=self.cat.storage/'temporary'/'own';raw.mkdir(parents=True)
        self.cat.event('WORK_DIRECTORY',{'temporary':'temporary/own'},run)
        for kind in ('L1R','L2W'):
            artifact_path=self.cat.storage/(run+'_'+kind+'.nc');artifact_path.write_bytes(kind.encode())
            self.cat.artifact(run,kind,artifact_path,{})
        self.cat.finish(run,'SUCCEEDED','TECHNICAL_PASSED')
        with patch('oceanos.pipeline.shutil.rmtree',side_effect=OSError):
            with self.assertRaises(OSError): cleanup(self.cat,run)
        row=self.cat.db.execute('SELECT estado,limpieza FROM ejecuciones WHERE id=?',(run,)).fetchone()
        self.assertEqual(tuple(row),('SUCCEEDED','FAILED'))
        self.assertEqual(cleanup(self.cat,run),'DELETED')

    def test_exclusive_writer(self):
        with exclusive(self.cat.storage):
            with self.assertRaises(RuntimeError):
                with exclusive(self.cat.storage): pass

    def test_l1r_reuse_before_download(self):
        # Un L1R validado y checksum comparable basta: la red no debe llamarse.
        data=source(sha256='local-sha');_,v=self.version(data)
        runner=object.__new__(Pipeline);runner.catalog=self.cat;runner.config=self.config;runner.engine={}
        runner.acolite=ACOLITE;runner.roots=[];runner.wait=lambda _:None;runner.metrics=[]
        _,correction=runner.keys(data)
        parent_run=self.cat.start(v,self.config,'old-products',correction)
        path=self.cat.storage/'parent.nc';path.write_bytes(b'L1R')
        artifact=self.cat.artifact(parent_run,'L1R',path,{})
        self.cat.finish(parent_run,'SUCCEEDED','TECHNICAL_PASSED')
        calls=[]
        def fake(operation,**args):
            calls.append(operation)
            self.assertTrue(args['derive'])
            out=Path(args['output']);out.mkdir();result=out/'new.nc';result.write_bytes(b'L2W')
            intermediate=out/'transient_L2R.nc';intermediate.write_bytes(b'L2R')
            return {'files':{'l1r':str(path),'l2r':str(intermediate),'l2w':str(result)},'science_metadata':{},'settings':{},'environment':{}}
        runner.call=fake
        report={'variables':{'l1r':[],'l2r':[],'l2w':[]},'grid':{},'technical':'PASSED','scientific':'PENDING'}
        with patch('oceanos.pipeline.validate',return_value=report):
            run=runner.run(v)
        self.assertEqual(calls,['process'])
        self.assertFalse(list((self.cat.storage/'runs'/run).rglob('*L2R*')))
        self.assertFalse(list((self.cat.storage/'runs'/run).rglob('*.json')))
        self.assertEqual(self.cat.db.execute("SELECT count(*) FROM artefactos WHERE run_id=? AND tipo='L2R'",(run,)).fetchone()[0],0)
        self.assertEqual(self.cat.db.execute('SELECT parent_artifact_id FROM ejecuciones WHERE id=?',(run,)).fetchone()[0],artifact)

    def test_failed_recoverable_source_is_cleaned_after_retries(self):
        _,v=self.version();run=self.cat.start(v,self.config,'a','b')
        raw=self.cat.storage/'temporary'/run;raw.mkdir(parents=True);(raw/'partial.zip').touch()
        self.cat.event('WORK_DIRECTORY',{'temporary':str(raw.relative_to(self.cat.storage))},run)
        for attempt in range(3): self.cat.event('ATTEMPT_FAILED',{'attempt':attempt+1},run)
        self.cat.finish(run,'FAILED')
        self.assertEqual(cleanup(self.cat,run),'DELETED')
        self.assertFalse(raw.exists())
        self.assertEqual(self.cat.db.execute('SELECT estado FROM ejecuciones WHERE id=?',(run,)).fetchone()[0],'FAILED')



class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.config=profile(ROOT/'config/aoi/lapargera_v1/project.yaml')

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
            self.assertEqual(cat.db.execute("SELECT count(*) FROM consultas WHERE estado='FAILED'").fetchone()[0],3)
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


if __name__=='__main__': unittest.main()
