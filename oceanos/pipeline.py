"""Orquestación secuencial, reintentos y conservación de historial."""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
import tempfile
from pathlib import Path
from .config import ROOT, canonical, digest, disk_bytes, file_hash
from .native import identity, eligible
from .validation import validate


class Pipeline:
    """Orquesta búsqueda, adquisición, procesamiento y registro de una escena a la vez."""
    def __init__(self, catalog, config, acolite, wait=time.sleep):
        """Guarda catálogo y perfil y calcula la identidad del motor ACOLITE."""
        self.catalog, self.config = catalog, config
        self.acolite = Path(acolite).resolve()
        self.engine = identity(self.acolite)
        self.wait = wait
        self.roots = [catalog.storage, self.acolite/'data', self.acolite/'scratch']
        self.metrics = []

    def notify(self, kind, details, run=None, query=None):
        """Imprime un evento y lo registra en el catálogo."""
        print(kind+': '+canonical(details), flush=True)
        self.catalog.event(kind,details,run,query)

    def call(self, operation, timeout=3600, **arguments):
        """Ejecuta una operación de ACOLITE en un proceso aislado (oceanos.worker).

        Los argumentos y el resultado viajan como JSON en una carpeta temporal. El proceso se
        corta si supera `timeout` segundos o el presupuesto de disco.
        """
        # JSON únicamente como transporte efímero entre procesos actual y el de ACOLITE; no es otro registro.
        temporary = self.catalog.storage/'temporary'
        temporary.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix='stage_', dir=temporary) as stage:
            # Se crea la peticion y se crea el archivo de resultado; el worker lo escribe al terminar.
            request, result = Path(stage)/'request.json', Path(stage)/'result.json'
            request.write_text(canonical({'operation':operation,'acolite':str(self.acolite),**arguments}))
            if disk_bytes(self.roots) >= self.config['budget']:
                raise RuntimeError('Presupuesto temporal agotado')
            # Ejecuta un proceso aislado de ACOLITE. usa (oceanos.worker.py)
            process = subprocess.Popen([sys.executable,'-m','oceanos.worker',str(request),str(result)],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True)
            try:
                # Revisa el estado del proceso aislado anterior cada 2 segundos.
                while process.poll() is None:
                    if time.monotonic()-started > timeout:
                        raise TimeoutError('Tiempo máximo de etapa agotado')
                    if disk_bytes(self.roots) >= self.config['budget']:
                        raise RuntimeError('Presupuesto temporal agotado')
                    self.wait(2)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
                raise
            # Lee la respuesta del proceso aislado y los registra
            response = json.loads(result.read_text()) if result.exists() else {'ok':False,'error':'WorkerExit'}
            self.metrics.append({'stage':operation, 'seconds':round(time.monotonic()-started,3),
                                 'rss_bytes':response.get('peak_rss_bytes'), 'ok':response['ok']})
            if process.returncode or not response['ok']:
                raise RuntimeError('Etapa '+operation+' falló: '+response.get('error','WorkerExit'))
            return response['result']

    def retry(self, function, run=None):
        """Ejecuta `function` con los reintentos y esperas del perfil; relanza el último error."""
        attempts = self.config['input']['transient_attempts_total']
        delays = self.config['input']['retry_wait_seconds']
        for attempt in range(attempts):
            try:
                return function()
            except Exception as error:
                self.notify('ATTEMPT_FAILED',{'attempt':attempt+1,'error':type(error).__name__},run)
                if attempt+1 == attempts:
                    raise
                self.wait(delays[attempt])

    def search(self):
        """Consulta el proveedor del perfil, registra las versiones observadas y devuelve sus ids."""
        # Sentinel-2: SAFE desde CDSE. Landsat: TAR desde USGS.
        provider = 'CDSE' if self.config['family']=='sentinel2' else 'USGS'
        versions = []
        batch = uuid.uuid4().hex
        parent = None
        # Intentos de consulta.
        for attempt in range(self.config['input']['transient_attempts_total']):
            # Registramos intento en la tabla Consultas para no repetir futuro trabajo paralelo
            query = self.catalog.query(provider
                                        ,{k:self.config[k] for k in ('aoi','family','start','end','cloud')}
                                        ,batch
                                        ,parent)
            try:
                # Instancia aislada de ACOLITE for search.
                response = self.call('query', timeout=900, provider=provider, config=self.config)
                # Registro de versiones observadas.
                for source in response['sources']:
                    versions.append(self.catalog.observe(query,source))
                # Actualizar estados de la consulta(tConsulta) y notificar(tEventos).
                self.catalog.finish_query(query,'SUCCEEDED',response['completeness'])
                self.notify('QUERY_FINISHED',{'provider':provider,'count':len(response['sources']),
                                             'completeness':response['completeness'],
                                             'excluded_by_profile':response.get('excluded_by_profile',[])},query=query)
                break
            except Exception as error:
                self.catalog.finish_query(query,'FAILED',error=type(error).__name__)
                self.notify('QUERY_FAILED',{'provider':provider,'attempt':attempt+1,'error':type(error).__name__},query=query)
                parent = query
                if attempt+1 == self.config['input']['transient_attempts_total']:
                    raise
                self.wait(self.config['input']['retry_wait_seconds'][attempt])
        return list(dict.fromkeys(versions))

    def keys(self, source):
        """Calcula processing_key (resultado final) y correction_key (corrección atmosférica)."""
        # Metadata administrativa, fechas de consulta y rutas de salida no cambian ciencia.
        scientific = {k:v for k,v in self.config['native'].items() if k not in ['l2w_parameters','rgb_rhot','rgb_rhos']}
        content = {'provider':source['provider'],'product':source['product'],
                   'format':source['format'],'sha256':source.get('sha256'),
                   'baseline':source['identity']['baseline']}
        correction = digest({'source':content,'aoi':self.config['aoi'], 'settings':scientific,
                             'grid':self.config['grid'],'engine':self.engine})
        processing = digest({'correction':correction,'products':self.config['products']})
        return processing, correction

    def run(self, version, local_l1r=None, force=False):
        """Procesa una versión de principio a fin y devuelve el id de la ejecución.

        Reutiliza L2W o L1R verificados si existen; si no, adquiere, extrae y procesa. Al
        terminar valida, registra L1R/L2W y limpia los temporales.
        """
        source = self.catalog.verified_source(self.catalog.source(version))
        if not eligible(source,self.config):
            raise ValueError('Versión fuera del perfil solicitado')
        # Persistir el intento antes de adquirir; archivos aislados por run_id.
        processing, correction = self.keys(source)
        run = self.catalog.start(version,self.config,processing,correction)
        folder = self.catalog.storage/'runs'/run
        raw = self.catalog.storage/'temporary'/run
        folder.mkdir(parents=True)
        self.metrics = []
        self.catalog.event('WORK_DIRECTORY',{'path':str(folder.relative_to(self.catalog.storage)),
                                            'temporary':str(raw.relative_to(self.catalog.storage))},run)
        try:
            cached_output = self.catalog.reusable(processing) if source.get('sha256') and not force else None
            if cached_output:
                self.catalog.finish(run,'SKIPPED',validation='TECHNICAL_PASSED')
                self.notify('SKIPPED',{'existing_run':cached_output['run_id'],'scientific':'PENDING'},run)
                return run
            cached_parent = self.catalog.reusable(correction,correction=True) if source.get('sha256') and not force else None
            if cached_parent:
                acquired = {'source':source}
            elif local_l1r:
                source = {**source,'sha256':file_hash(local_l1r)}
                acquired = {'input':str(Path(local_l1r).resolve()),'source':source}
            else:
                acquired = self.retry(lambda:self.call('acquire',source=source,raw=str(raw)),run)
                source = acquired['source']
            query = self.catalog.query(source['provider'],{'action':'fuente_verificada','run':run})
            verified_version = self.catalog.observe(query,source)
            self.catalog.finish_query(query,'SUCCEEDED')
            processing,correction = self.keys(source)
            with self.catalog.db:
                self.catalog.db.execute('UPDATE ejecuciones SET version_id=?,processing_key=?,correction_key=? WHERE id=?',
                                        (verified_version,processing,correction,run))
            # Sin SHA verificado no se omite ni se deriva automáticamente.
            reusable = self.catalog.reusable(processing) if source.get('sha256') and not force else None
            if reusable:
                self.catalog.finish(run,'SKIPPED',validation='TECHNICAL_PASSED')
                self.notify('SKIPPED',{'existing_run':reusable['run_id'],'scientific':'PENDING'},run)
                return run
            parent = self.catalog.reusable(correction,correction=True) if source.get('sha256') and not force else None
            derive = local_l1r is not None or parent is not None
            if parent:
                input_path = self.catalog.storage/parent['ruta']
                with self.catalog.db:
                    self.catalog.db.execute('UPDATE ejecuciones SET parent_artifact_id=? WHERE id=?',(parent['id'],run))
                self.notify('REUSE_L1R',{'parent_artifact_id':parent['id']},run)
            elif local_l1r:
                # Copia propia: resultados externos nunca se borran ni se sobrescriben.
                input_path = folder/'source_L1R.nc'
                if Path(local_l1r).stat().st_size + disk_bytes(self.roots) >= self.config['budget']:
                    raise RuntimeError('Presupuesto insuficiente para conservar L1R')
                shutil.copyfile(local_l1r,input_path)
            elif acquired.get('archive'):
                extracted = self.call('extract',archive=acquired['archive'],raw=str(raw),
                                      available=self.config['budget']-disk_bytes(self.roots))
                input_path = extracted['input']
            else:
                input_path = acquired['input']
            if derive:
                validate({'l1r':str(input_path)},self.config)
            settings = folder/'settings.txt'
            settings.write_text('\n'.join(k+'='+str(v) for k,v in sorted(self.config['native'].items()))+'\n')
            result = self.call('process',input=str(input_path),settings=str(settings),
                               output=str(folder/'output'),derive=derive)
            files = result['files']
            report = validate(files,self.config)
            # Solo L1R y L2W persisten; L2R se usa para QA y metadata, luego se elimina.
            for level in ('l1r','l2w'):
                if parent and level=='l1r':
                    continue
                self.catalog.artifact(run,level.upper(),files[level],
                                      {'variables':report['variables'][level],'grid':report['grid']})
            summary = {'validation':report, 'engine':self.engine,
                       'science':result['science_metadata'], 'settings':result['settings'],
                       'environment':result['environment'], 'metrics':self.metrics}
            self.catalog.finish(run,'SUCCEEDED','TECHNICAL_PASSED',provenance=digest(summary),summary=summary)
            # Publicación registrada antes de retirar intermediarios propios.
            retained = {Path(files[k]).resolve() for k in ('l1r','l2w')}
            for path in folder.rglob('*'):
                if path.is_file() and path.resolve() not in retained:
                    path.unlink()
            disposition = cleanup(self.catalog,run)
            self.notify('TECHNICAL_PASSED',{'run':run,'scientific':'PENDING','cleanup':disposition},run)
            return run
        except BaseException as error:
            completed = self.catalog.db.execute('SELECT estado FROM ejecuciones WHERE id=?',(run,)).fetchone()[0]
            if completed=='SUCCEEDED':
                with self.catalog.db:
                    self.catalog.db.execute("UPDATE ejecuciones SET limpieza='FAILED' WHERE id=?",(run,))
                self.notify('CLEANUP_FAILED',{'error':type(error).__name__},run)
                return run
            state = 'INTERRUPTED' if isinstance(error,(KeyboardInterrupt,SystemExit)) else 'FAILED'
            self.catalog.finish(run,state,error=type(error).__name__,summary={'metrics':self.metrics})
            self.notify(state,{'error':type(error).__name__,'raw':'RETAINED'},run)
            if state=='FAILED':
                try:
                    disposition = cleanup(self.catalog,run)
                    self.notify('CLEANUP_POLICY',{'result':disposition},run)
                except OSError:
                    self.notify('CLEANUP_FAILED',{'raw':'RETAINED'},run)
            raise

    def batch(self, versions, force=False):
        """Procesa cada producto una vez y devuelve las versiones que fallaron."""
        groups = {}
        for version in versions:
            source = self.catalog.source(version)
            # Identidad/baseline exactas; nunca deduplicar únicamente por fecha.
            key = (source['identity']['acquisition_key'],source['identity']['baseline'],source['product'])
            # Una ejecución por producto: la primera versión observada.
            groups.setdefault(key,version)
        failed = []
        for version in groups.values():
            try:
                self.run(version,force=force)
            except Exception:
                failed.append(version)
        return failed


def cleanup(catalog, run):
    """Borra los temporales de una ejecución si la política lo permite y devuelve el resultado.

    Se borra si L1R y L2W están verificados, si se agotaron los reintentos de una fuente
    recuperable o si la ejecución fue interrumpida; en otro caso se aplaza.
    """
    row = catalog.db.execute('SELECT * FROM ejecuciones WHERE id=?',(run,)).fetchone()
    if not row:
        raise ValueError('Ejecución inexistente')
    source = catalog.source(row['version_id'])
    attempts = catalog.db.execute("SELECT count(*) FROM eventos WHERE run_id=? AND tipo='ATTEMPT_FAILED'",(run,)).fetchone()[0]
    required = json.loads(row['configuracion'])['input']['transient_attempts_total']
    recoverable = source['provider'] in ('CDSE','USGS') and bool(source.get('id'))
    exhausted = row['estado']=='FAILED' and attempts >= required and recoverable
    artifacts = catalog.db.execute("SELECT * FROM artefactos WHERE run_id=? AND tipo IN ('L1R','L2W')",(run,)).fetchall()
    kinds = {a['tipo'] for a in artifacts if catalog.available(a)}
    if row['parent_artifact_id']:
        parent = catalog.db.execute('SELECT * FROM artefactos WHERE id=?',(row['parent_artifact_id'],)).fetchone()
        if parent and parent['tipo']=='L1R' and catalog.available(parent): kinds.add('L1R')
    complete = row['estado']=='SUCCEEDED' and row['validacion']=='TECHNICAL_PASSED' and kinds=={'L1R','L2W'}
    # Interrumpida (marcada por recover): sus descargas/salidas parciales nunca se reutilizan;
    # un nuevo run vuelve a adquirir la fuente, así que solo ocupan presupuesto.
    interrupted = row['estado']=='INTERRUPTED'
    if not complete and not exhausted and not interrupted:
        with catalog.db:
            catalog.db.execute("UPDATE ejecuciones SET limpieza='DEFERRED_VALIDATION' WHERE id=?",(run,))
        catalog.event('CLEANUP_DEFERRED',{'reason':'No se cumplen los criterios técnicos, de reintentos agotados ni de interrupción para limpiar'},run)
        return 'DEFERRED_VALIDATION'
    reason = 'L1R_y_L2W_verificados' if complete else ('reintentos_agotados_fuente_recuperable' if exhausted else 'ejecucion_interrumpida')
    catalog.event('CLEANUP_AUTHORIZED',{'reason':reason},run)
    # Carpeta de trabajo de un run interrumpido solo si no registró artefactos (corte entre registro y cierre).
    registered = catalog.db.execute('SELECT count(*) FROM artefactos WHERE run_id=?',(run,)).fetchone()[0]
    keys = [('temporary','temporary')] + ([('path','runs')] if interrupted and not registered else [])
    events = catalog.db.execute("SELECT detalles FROM eventos WHERE run_id=? AND tipo='WORK_DIRECTORY'",(run,)).fetchall()
    for event, (key, root) in ((e, k) for e in events for k in keys):
        relative = json.loads(event['detalles']).get(key)
        if not relative:
            continue
        target = catalog.storage/relative
        allowed = (catalog.storage/root).resolve()
        if target.is_symlink() or not target.resolve().is_relative_to(allowed) or target.resolve()==allowed:
            raise ValueError('Ruta de limpieza fuera de la carpeta de ejecución')
        try:
            if target.exists():
                shutil.rmtree(target)
        except OSError:
            with catalog.db:
                catalog.db.execute("UPDATE ejecuciones SET limpieza='FAILED' WHERE id=?",(run,))
            catalog.event('CLEANUP_FAILED',{},run)
            raise
    with catalog.db:
        catalog.db.execute("UPDATE ejecuciones SET limpieza='DELETED' WHERE id=?",(run,))
    catalog.event('CLEANUP_FINISHED',{},run)
    return 'DELETED'


def recover(catalog):
    """Registra interrupciones y limpia lo parcial de toda ejecución INTERRUPTED pendiente.

    Bajo el bloqueo exclusivo ningún run está vivo: lo que queda en STARTED está abandonado.
    También cubre Ctrl+C, que marca INTERRUPTED sin pasar por aquí. Un fallo de borrado no
    detiene el arranque: queda limpieza='FAILED' y se reintenta en el próximo recover.
    """
    marked = catalog.recover()
    pending = catalog.db.execute("SELECT id FROM ejecuciones WHERE estado='INTERRUPTED' "
                                 "AND limpieza!='DELETED' ORDER BY inicio").fetchall()
    cleaned, failed = [], []
    for (run,) in pending:
        try:
            cleanup(catalog,run)
            cleaned.append(run)
        except Exception as error:
            # cleanup ya registra los OSError de borrado; el resto (p. ej. ruta fuera de storage) se registra aquí.
            if not isinstance(error,OSError):
                with catalog.db:
                    catalog.db.execute("UPDATE ejecuciones SET limpieza='FAILED' WHERE id=?",(run,))
                catalog.event('CLEANUP_FAILED',{'error':type(error).__name__},run)
            failed.append(run)
    return {'interrumpidas':marked,'limpiadas':cleaned,'limpieza_fallida':failed}
