"""Orquestación secuencial, reintentos y conservación de historial."""
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from .config import ROOT, canonical, digest, disk_bytes, file_hash, received_bytes
from .native import identity, eligible, l1_bytes
from .validation import validate

STAGES = {'query':'consulta', 'extract':'extracción', 'process':'ACOLITE'}


class Pipeline:
    """Orquesta búsqueda, adquisición, procesamiento y registro de una escena a la vez."""
    # Barra de progreso opcional (oceanos.progress.Progress) y último proceso creado por run().
    progress = None
    current_run = None
    # Informe de la última consulta al proveedor (sin fuentes), para que el CLI lo explique.
    last_query = None

    def __init__(self, catalog, config, acolite, wait=time.sleep, progress=None):
        """Guarda catálogo y perfil y calcula la identidad del motor ACOLITE."""
        self.catalog, self.config = catalog, config
        self.acolite = Path(acolite).resolve()
        self.engine = identity(self.acolite)
        self.wait = wait
        self.progress = progress
        self.roots = [catalog.storage, self.acolite/'data', self.acolite/'scratch']
        self.metrics = []

    def notify(self, kind, message, process=None, scene=None, echo=True):
        """Registra un evento legible en el catálogo y, con `echo`, lo imprime."""
        if echo:
            if self.progress:
                self.progress.clear()
            print(f'{kind}: {message}', flush=True)
        self.catalog.event(kind, message, process, scene)

    def watch(self, operation, pid, stage, started, arguments, state):
        """Actualiza la barra de progreso de la etapa en curso del proceso aislado.

        La descarga nativa guarda el archivo solo al terminar, así que se miden los bytes que
        recibe el proceso desde que cargó ACOLITE. Las demás etapas se comparan con su
        duración habitual en el catálogo.
        """
        if not self.progress:
            return
        elapsed = time.monotonic()-started
        if operation != 'acquire':
            if operation not in state:
                state[operation] = self.catalog.stage_seconds(operation)
            self.progress.stage(STAGES.get(operation,operation),elapsed,state[operation])
            return
        baseline, current = Path(stage)/'baseline', received_bytes(pid)
        if current is None or not baseline.exists():
            self.progress.stage('descarga: conectando',elapsed)
            return
        done = max(current-int(baseline.read_text() or 0),0)
        total = l1_bytes(arguments['source'])
        if total and done > total:
            # Lecturas posteriores a la descarga: hashes SHA-256/MD5 del archivo.
            self.progress.stage('descarga completa, verificando checksum',elapsed)
            return
        # Velocidad promedio desde el primer byte recibido.
        instant = time.monotonic()
        if done and 'first' not in state:
            state['first'] = (instant,done)
        first = state.get('first')
        rate = (done-first[1])/(instant-first[0]) if first and instant-first[0] >= 1 else None
        self.progress.download(done,total,rate,elapsed)

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
            state = {}
            try:
                # Revisa el estado del proceso aislado anterior cada 2 segundos.
                while process.poll() is None:
                    if time.monotonic()-started > timeout:
                        raise TimeoutError('Tiempo máximo de etapa agotado')
                    if disk_bytes(self.roots) >= self.config['budget']:
                        raise RuntimeError('Presupuesto temporal agotado')
                    self.watch(operation,process.pid,stage,started,arguments,state)
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

    def retry(self, function, process=None, scene=None):
        """Ejecuta `function` con los reintentos y esperas del perfil; relanza el último error."""
        attempts = self.config['input']['transient_attempts_total']
        delays = self.config['input']['retry_wait_seconds']
        for attempt in range(attempts):
            try:
                return function()
            except Exception as error:
                self.notify('INTENTO_FALLIDO', f'Descarga, intento {attempt+1} de {attempts}: {type(error).__name__}',
                            process, scene)
                if attempt+1 == attempts:
                    raise
                self.wait(delays[attempt])

    def search(self):
        """Consulta el proveedor del perfil, registra las escenas observadas y devuelve sus nombres."""
        # Sentinel-2: SAFE desde CDSE. Landsat: TAR desde USGS.
        provider = 'CDSE' if self.config['family']=='sentinel2' else 'USGS'
        attempts = self.config['input']['transient_attempts_total']
        for attempt in range(attempts):
            search = self.catalog.search_start(provider, self.config, attempt+1)
            try:
                # Proceso aislado de ACOLITE para la consulta.
                response = self.call('query', timeout=900, provider=provider, config=self.config)
                scenes = [self.catalog.upsert_scene(source) for source in response['sources']]
                self.last_query = {'provider':provider,'count':len(response['sources']),
                                   **{k:v for k,v in response.items() if k!='sources'}}
                self.catalog.search_finish(search, 'OK', self.last_query)
                return list(dict.fromkeys(scenes))
            except Exception as error:
                self.catalog.search_finish(search, 'FALLIDA', error=type(error).__name__)
                self.notify('BUSQUEDA_FALLIDA', f'{provider}, intento {attempt+1} de {attempts}: {type(error).__name__}')
                if attempt+1 == attempts:
                    raise
                self.wait(self.config['input']['retry_wait_seconds'][attempt])

    def keys(self, source):
        """Calcula la clave de resultado (L2W) y la de corrección atmosférica (L1R)."""
        # Metadata administrativa, fechas de consulta y rutas de salida no cambian ciencia.
        scientific = {k:v for k,v in self.config['native'].items() if k not in ['l2w_parameters','rgb_rhot','rgb_rhos']}
        content = {'provider':source['provider'],'product':source['product'],
                   'format':source['format'],'sha256':source.get('sha256'),
                   'baseline':source['identity']['baseline']}
        correction = digest({'source':content,'aoi':self.config['aoi'], 'settings':scientific,
                             'grid':self.config['grid'],'engine':self.engine})
        processing = digest({'correction':correction,'products':self.config['products']})
        return processing, correction

    def skip(self, process, scene, existing):
        """Cierra un proceso como OMITIDO porque ya existe un L2W verificado equivalente."""
        self.catalog.finish(process, 'OMITIDO', 'TECNICA_OK')
        self.catalog.update(process, limpieza='NO_APLICA')
        self.notify('OMITIDO', f'Ya existe un L2W equivalente en el proceso {existing["proceso"]}', process, scene)
        return process

    def run(self, scene, source=None, local_l1r=None, force=False):
        """Procesa una escena de principio a fin y devuelve el id del proceso.

        `source` sustituye la fuente del catálogo (archivo local de `run --source`/`derive`).
        Reutiliza L2W o L1R verificados si existen; si no, adquiere, extrae y procesa. Al
        terminar valida, registra L1R/L2W y limpia los temporales.
        """
        remote = source is None
        source = source or self.catalog.source(scene)
        if not eligible(source,self.config):
            raise ValueError('Escena fuera del perfil solicitado')
        result_key, correction_key = self.keys(source)
        kind = 'DERIVADO' if local_l1r else ('LOCAL' if source.get('local') else 'DESCARGA')
        process = self.catalog.start(scene, kind, self.config, result_key, correction_key)
        self.current_run = process
        folder = self.catalog.storage/self.catalog.process(process)['carpeta']
        raw = self.catalog.storage/'temporary'/str(process)
        folder.mkdir(parents=True)
        self.metrics = []
        try:
            cached = self.catalog.reusable(result_key) if source.get('sha256') and not force else None
            if cached:
                return self.skip(process, scene, cached)
            parent = self.catalog.reusable(correction_key,correction=True) if source.get('sha256') and not force else None
            if parent:
                acquired = {'source':source}
            elif local_l1r:
                source = {**source,'sha256':file_hash(local_l1r)}
                acquired = {'input':str(Path(local_l1r).resolve()),'source':source}
            else:
                acquired = self.retry(lambda:self.call('acquire',source=source,raw=str(raw)),process,scene)
                source = acquired['source']
                self.record_download(process,acquired.get('archive'),source)
                if remote:
                    # Guarda el SHA-256 comprobado para reconocer la misma fuente en el futuro.
                    self.catalog.upsert_scene(source, seen=False)
            result_key, correction_key = self.keys(source)
            self.catalog.update(process, clave_resultado=result_key, clave_correccion=correction_key)
            # Sin SHA verificado no se omite ni se deriva automáticamente.
            cached = self.catalog.reusable(result_key) if source.get('sha256') and not force else None
            if cached:
                return self.skip(process, scene, cached)
            parent = parent or (self.catalog.reusable(correction_key,correction=True) if source.get('sha256') and not force else None)
            derive = local_l1r is not None or parent is not None
            if parent:
                input_path = self.catalog.storage/parent['ruta']
                self.catalog.update(process, l1r_padre=parent['proceso'], tipo='DERIVADO')
                self.notify('REUTILIZA_L1R', f'Se regenera desde el L1R del proceso {parent["proceso"]}', process, scene)
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
                               output=str(folder),derive=derive)
            files = result['files']
            report = validate(files,self.config)
            # Solo L1R y L2W persisten; L2R se usa para QA y metadata, luego se elimina.
            for level in ('l1r','l2w'):
                if parent and level=='l1r':
                    continue
                self.catalog.artifact(process,level.upper(),files[level])
            self.catalog.finish(process,'OK','TECNICA_OK',qa=report,engine=self.engine,
                                science=result['science_metadata'],settings=result['settings'],
                                environment=result['environment'],metrics=self.metrics)
            # Publicación registrada antes de retirar intermediarios propios.
            retained = {Path(files[k]).resolve() for k in ('l1r','l2w')}
            for path in sorted(folder.rglob('*'), reverse=True):
                if path.is_file() and path.resolve() not in retained:
                    path.unlink()
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            disposition = cleanup(self.catalog,process)
            self.notify('TECNICA_OK', f'L1R y L2W registrados en {self.catalog.process(process)["carpeta"]}; '
                        f'limpieza {disposition}; validación científica pendiente', process, scene)
            return process
        except BaseException as error:
            if self.catalog.process(process)['estado']=='OK':
                self.catalog.update(process, limpieza='FALLIDA')
                self.notify('LIMPIEZA_FALLIDA', type(error).__name__, process, scene)
                return process
            state = 'INTERRUMPIDO' if isinstance(error,(KeyboardInterrupt,SystemExit)) else 'FALLIDO'
            self.record_download(process)
            self.catalog.finish(process,state,error=type(error).__name__,metrics=self.metrics)
            print(f'{state}: {type(error).__name__} (temporales conservados)', flush=True)
            if state=='FALLIDO':
                try:
                    cleanup(self.catalog,process)
                except OSError:
                    self.notify('LIMPIEZA_FALLIDA', 'Temporales conservados', process, scene)
            raise

    def record_download(self, process, archive=None, source=None):
        """Guarda en el proceso los minutos de la descarga exitosa, sus MB y los intentos.

        Los intentos cuentan los fallidos (eventos INTENTO_FALLIDO, incluidos los cortados por
        tiempo) más el exitoso; sin intentos de descarga no se escribe nada.
        """
        failed = self.catalog.failed_attempts(process)
        succeeded = [m for m in self.metrics if m['stage']=='acquire' and m['ok']]
        if not failed and not succeeded:
            return
        size = None
        if succeeded:
            size = Path(archive).stat().st_size if archive and Path(archive).is_file() else None
            size = size or l1_bytes(source or {})
        row = self.catalog.process(process)
        previous = None if row['descarga_mb'] is None else row['descarga_mb']*1e6
        self.catalog.downloaded(process,succeeded[-1]['seconds'] if succeeded else None,size or previous,
                                failed+len(succeeded))

    def batch(self, scenes, force=False):
        """Procesa las escenas una a una y devuelve el resumen del lote.

        Cada escena queda PROCESADA (procesada u omitida por existir) o FALLIDA (se reintenta
        en el próximo run). Devuelve {'runs': procesos creados, 'failed': escenas fallidas,
        'seconds': duración}.
        """
        started = time.monotonic()
        scenes = list(dict.fromkeys(scenes))
        runs, failed = [], []
        for index, scene in enumerate(scenes, 1):
            if self.progress:
                row = self.catalog.db.execute('SELECT satelite, fecha_utc, tile FROM escenas WHERE escena=?',(scene,)).fetchone()
                self.progress.scene(index,len(scenes),f"{row['satelite']} {row['fecha_utc']} {row['tile']}")
            self.current_run = None
            try:
                self.run(scene,force=force)
                self.catalog.scene_state(scene,'PROCESADA')
            except Exception:
                failed.append(scene)
                self.catalog.scene_state(scene,'FALLIDA')
            if self.current_run:
                runs.append(self.current_run)
        if self.progress:
            self.progress.clear()
        return {'runs':runs,'failed':failed,'seconds':round(time.monotonic()-started,3)}


def cleanup(catalog, process):
    """Borra los temporales de un proceso si la política lo permite y devuelve el resultado.

    Se borra si L1R y L2W están verificados, si se agotaron los reintentos de una fuente
    recuperable o si el proceso fue interrumpido; en otro caso se aplaza.
    """
    row = catalog.process(int(process))
    process = row['id']
    if row['tipo']=='IMPORTADO':
        # Archivos copiados a mano: no hay temporales propios y nunca se borran.
        return 'NO_APLICA'
    source = catalog.source(row['escena'])
    required = json.loads(row['detalle'] or '{}').get('perfil',{}).get('input',{}).get('transient_attempts_total',3)
    recoverable = source['provider'] in ('CDSE','USGS') and bool(source.get('id'))
    exhausted = row['estado']=='FALLIDO' and catalog.failed_attempts(process) >= required and recoverable
    kinds = {kind for kind in ('L1R','L2W') if catalog.available(row,kind)}
    if row['l1r_padre']:
        parent = catalog.process(row['l1r_padre'])
        if catalog.available(parent,'L1R'):
            kinds.add('L1R')
    complete = row['estado']=='OK' and row['validacion']=='TECNICA_OK' and kinds=={'L1R','L2W'}
    # Interrumpido (marcado por recover): sus descargas/salidas parciales nunca se reutilizan;
    # un nuevo run vuelve a adquirir la fuente, así que solo ocupan presupuesto.
    interrupted = row['estado']=='INTERRUMPIDO'
    if not complete and not exhausted and not interrupted:
        catalog.update(process, limpieza='APLAZADA')
        catalog.event('LIMPIEZA_APLAZADA','No se cumplen los criterios técnicos, de reintentos agotados ni de interrupción',
                      process,row['escena'])
        return 'APLAZADA'
    targets = [('temporary/'+str(process),'temporary')]
    # Carpeta de un proceso interrumpido solo si no registró archivos (corte entre registro y cierre).
    if interrupted and not row['l1r'] and not row['l2w'] and row['carpeta']:
        targets.append((row['carpeta'],'runs'))
    for relative, root in targets:
        target = catalog.storage/relative
        allowed = (catalog.storage/root).resolve()
        if target.is_symlink() or not target.resolve().is_relative_to(allowed) or target.resolve()==allowed:
            raise ValueError('Ruta de limpieza fuera de la carpeta del proceso')
        try:
            if target.exists():
                shutil.rmtree(target)
        except OSError:
            catalog.update(process, limpieza='FALLIDA')
            catalog.event('LIMPIEZA_FALLIDA','No se pudo borrar '+relative,process,row['escena'])
            raise
    catalog.update(process, limpieza='HECHA')
    reason = 'L1R y L2W verificados' if complete else ('reintentos agotados' if exhausted else 'proceso interrumpido')
    catalog.event('LIMPIEZA_HECHA','Temporales borrados: '+reason,process,row['escena'])
    return 'HECHA'


def recover(catalog):
    """Registra interrupciones y limpia lo parcial de todo proceso INTERRUMPIDO pendiente.

    Bajo el bloqueo exclusivo ningún proceso está vivo: lo que queda EN_CURSO está abandonado.
    También cubre Ctrl+C, que marca INTERRUMPIDO sin pasar por aquí. Un fallo de borrado no
    detiene el arranque: queda limpieza FALLIDA y se reintenta en el próximo recover.
    """
    marked = catalog.recover()
    pending = catalog.db.execute("SELECT id FROM procesos WHERE estado='INTERRUMPIDO' "
                                 "AND limpieza!='HECHA' ORDER BY id").fetchall()
    cleaned, failed = [], []
    for (process,) in pending:
        try:
            cleanup(catalog,process)
            cleaned.append(process)
        except Exception as error:
            # cleanup ya registra los OSError de borrado; el resto (p. ej. ruta fuera de storage) se registra aquí.
            if not isinstance(error,OSError):
                catalog.update(process, limpieza='FALLIDA')
                catalog.event('LIMPIEZA_FALLIDA',type(error).__name__,process)
            failed.append(process)
    return {'interrumpidos':marked,'limpiados':cleaned,'limpieza_fallida':failed}
