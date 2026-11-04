"""Orquestación por escena (secuencial o en paralelo), reintentos y conservación de historial."""
import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import tempfile
import threading
from pathlib import Path
from .catalog import Catalog, place, satellite
from .config import ROOT, canonical, disk_bytes, file_hash, received_bytes
from .escenas import SENSOR_TAG, describe, verify
from .mascara import path_for as mask_path
from .native import identity, eligible, l1_bytes, scene_date, zones_for
from .validation import validate

STAGES = {'query':'consulta', 'extract':'extracción', 'clouds':'nubes', 'process':'ACOLITE', 'export':'exportación'}
# Motivos de fallo de descarga (oceanos.native.DownloadError) en palabras; HTTP_5xx se explica aparte.
REASONS = {'HTTP_401':'credenciales rechazadas (401)', 'HTTP_403':'sin permiso de descarga (403)',
           'HTTP_404':'producto no encontrado (404)', 'HTTP_429':'cuota del proveedor superada (429)',
           'TOKEN_HTTP_401':'credenciales CDSE rechazadas al pedir el token (401)',
           'SIN_CREDENCIALES':'faltan credenciales en ~/.netrc', 'CONEXION':'conexión cortada',
           'TIEMPO_AGOTADO':'el servidor dejó de responder', 'REDIRECCION_NO_CONFIABLE':'redirección a un host ajeno',
           'SIN_BOTON_DESCARGA':'EarthExplorer no mostró el botón de descarga',
           'SIN_URL_DESCARGA':'EarthExplorer no entregó la URL de descarga',
           'DESCARGA_RECHAZADA':'USGS rechazó la descarga',
           'RANGO_INVALIDO':'el servidor respondió un rango que no se pidió',
           'LOGIN_EARTHEXPLORER':'EarthExplorer no mostró el formulario de inicio de sesión',
           'M2M_SIN_BUNDLE':'USGS M2M no ofrece el Product Bundle de la escena',
           'M2M_SIN_URL':'USGS M2M no entregó la URL de descarga a tiempo',
           'AUXILIAR_POR_DEFECTO':'ACOLITE no consiguió los auxiliares MERRA-2 y usó valores por defecto; se reintenta',
           'PRESUPUESTO_SUPERIMAGEN':'se alcanzó el presupuesto de disco de la superimagen',
           'SIN_MASCARA':'falta la máscara de tierra de la zona (oceanos mascara)'}
# Fallos que no se arreglan esperando: se informan sin gastar más intentos.
FINAL = {'HTTP_401', 'HTTP_403', 'HTTP_404', 'TOKEN_HTTP_401', 'TOKEN_HTTP_400', 'SIN_CREDENCIALES',
         'REDIRECCION_NO_CONFIABLE', 'PRESUPUESTO_SUPERIMAGEN'}
# Espera mínima tras superar la cuota del proveedor (429) y máxima: si Retry-After pide más, no se
# espera; la escena queda FALLIDA para el próximo run (reintentos cortos, ver `retry`).
QUOTA_WAIT, QUOTA_WAIT_MAX = 30, 60


class StageError(RuntimeError):
    """Fallo de una etapa del proceso aislado con su motivo (código corto o tipo de excepción)."""
    def __init__(self, operation, reason, retry_after=None):
        super().__init__(f'Etapa {operation} falló: {reason}')
        self.reason, self.retry_after = reason, retry_after


def reason(error):
    """Motivo corto de un error para el catálogo: el código de la etapa o el tipo de excepción."""
    return getattr(error, 'reason', None) or type(error).__name__


def explain(code):
    """Motivo de fallo en palabras para eventos y mensajes."""
    if code.startswith('HTTP_5'):
        return f'error del servidor del proveedor ({code[5:]})'
    return REASONS.get(code, code)


# Espacio que se deja libre en el disco de storage, además del presupuesto de temporales.
DISK_MARGIN = 2e9


def roots(storage, acolite):
    """Carpetas del presupuesto de temporales: temporales de storage, LUT/auxiliares y scratch de ACOLITE.

    La superimagen tiene su propio presupuesto y el legado (runs, importados) no es temporal.
    """
    return [Path(storage)/'temporary', Path(acolite).resolve()/'data', Path(acolite).resolve()/'scratch']


def superimagen_bytes(storage):
    """Bytes ocupados por los productos finales en storage/superimagen."""
    return disk_bytes([Path(storage)/'superimagen'])


def product_estimate(config):
    """Bytes estimados de los COG de una escena en una zona, antes de tener mediciones.

    Float32 por variable más 10 bandas de calidad, sobre el rectángulo de la zona más grande; la
    compresión ZSTD y la tierra en NoData lo reducen a la mitad, aproximadamente.
    """
    pixels = max(z['grid']['shape_yx'][0]*z['grid']['shape_yx'][1] for z in config['zones'].values())
    rrs = {'sentinel2': 13, 'landsat': 9, 'olci': 21}[config['family']]
    layers = rrs + len(config['products']) - 1 + 10
    return int(pixels*4*layers*0.5)


def disk_free(path):
    """Bytes libres en el disco que contiene `path`."""
    return shutil.disk_usage(path).free


class Pipeline:
    """Orquesta búsqueda, adquisición, procesamiento y registro de escenas.

    Una instancia atiende una escena a la vez; en paralelo, cada hilo usa su copia (`clone`).
    """
    # Barra de progreso opcional (oceanos.progress.Progress) y último proceso creado por run().
    progress = None
    current_run = None
    # Reparto de CPU/RAM (oceanos.resources.Resources); sin él, el lote es secuencial.
    resources = None
    # Informe de la última consulta al proveedor (sin fuentes), para que el CLI lo explique.
    last_query = None
    # Verdadero si run() no descargó la última escena porque su adquisición ya estaba completa.
    found = None

    def __init__(self, catalog, config, acolite, wait=time.sleep, progress=None, resources=None):
        """Guarda catálogo y perfil y calcula la identidad del motor ACOLITE."""
        self.catalog, self.config = catalog, config
        self.acolite = Path(acolite).resolve()
        self.engine = identity(self.acolite)
        self.wait = wait
        self.progress = progress
        self.resources = resources
        self.roots = roots(catalog.storage, self.acolite)
        self.metrics = []

    def clone(self):
        """Copia para otro hilo: comparte perfil, progreso y recursos; abre su propia conexión SQLite."""
        twin = object.__new__(Pipeline)
        twin.__dict__.update(self.__dict__)
        twin.catalog = Catalog(self.catalog.storage)
        twin.metrics, twin.current_run = [], None
        return twin

    def say(self, text):
        """Imprime una línea sin pisar la barra de progreso."""
        if self.progress:
            self.progress.message(text)
        else:
            print(text, flush=True)

    def pause(self, seconds):
        """Espera entre reintentos; en paralelo se corta si se pidió detener el lote."""
        if self.resources:
            if self.resources.stop.wait(seconds):
                raise KeyboardInterrupt
        else:
            self.wait(seconds)

    def notify(self, kind, message, process=None, scene=None, echo=True):
        """Registra un evento legible en el catálogo y, con `echo`, lo imprime."""
        if echo:
            self.say(f'{kind}: {message}')
        self.catalog.event(kind, message, process, scene)

    def watch(self, operation, pid, stage, started, arguments, state):
        """Actualiza la barra de progreso de la etapa en curso del proceso aislado.

        La descarga CDSE escribe en streaming un `.part`, cuyo tamaño es el avance. La nativa de
        USGS guarda el archivo solo al terminar, así que se miden los bytes que recibe el proceso
        desde que cargó ACOLITE. Las demás etapas se comparan con su duración habitual.
        """
        if not self.progress:
            return
        elapsed = time.monotonic()-started
        if operation != 'acquire':
            if operation not in state:
                state[operation] = self.catalog.stage_seconds(operation)
            self.progress.stage(STAGES.get(operation,operation),elapsed,state[operation])
            return
        total = l1_bytes(arguments['source'])
        part = next(Path(arguments['raw']).glob('*.part'), None) if arguments.get('raw') else None
        written = None
        if part:
            # El .part se renombra al terminar: puede desaparecer entre glob y stat.
            with contextlib.suppress(OSError):
                written = part.stat().st_size
        baseline, current = Path(stage)/'baseline', received_bytes(pid)
        if written is not None:
            done = written
        elif current is None or not baseline.exists():
            self.progress.stage('descarga: conectando',elapsed)
            return
        else:
            done = max(current-int(baseline.read_text() or 0),0)
        if total and done > total and written is None:
            # Lecturas posteriores a la descarga: hashes SHA-256/MD5 del archivo.
            self.progress.stage('descarga completa, verificando checksum',elapsed)
            return
        # Velocidad promedio desde el primer byte recibido. Si cambia la medida (bytes del proceso
        # antes de crear el .part, tamaño del .part después), se reinicia para no restar magnitudes distintas.
        instant = time.monotonic()
        measure = 'part' if written is not None else 'proceso'
        if state.get('measure') != measure:
            state.pop('first', None)
            state['measure'] = measure
        if done and 'first' not in state:
            state['first'] = (instant,done)
        first = state.get('first')
        rate = (done-first[1])/(instant-first[0]) if first and instant-first[0] >= 1 else None
        self.progress.download(done,total,rate,elapsed)

    def used(self):
        """Bytes del presupuesto de temporales ya ocupados."""
        return disk_bytes(self.roots)

    def check_disk(self):
        """Detiene la etapa si se agotó el presupuesto de temporales o el disco está casi lleno."""
        if self.used() >= self.config['budget']:
            raise RuntimeError('Presupuesto temporal agotado')
        if disk_free(self.catalog.storage) < DISK_MARGIN:
            raise RuntimeError('Disco casi lleno')

    def call(self, operation, timeout=3600, day=None, **arguments):
        """Ejecuta una operación de ACOLITE en un proceso aislado (oceanos.worker).

        Los argumentos y el resultado viajan como JSON en una carpeta temporal. El proceso se
        corta si supera `timeout` segundos o el presupuesto de disco. Con `resources` espera a
        que su pico de RAM quepa, limita sus hilos numéricos y usa un scratch propio de ACOLITE;
        `day` (AAAAMMDD) impide dos ACOLITE a la vez de escenas del mismo día.
        """
        # JSON únicamente como transporte efímero entre procesos actual y el de ACOLITE; no es otro registro.
        temporary = self.catalog.storage/'temporary'
        temporary.mkdir(parents=True, exist_ok=True)
        queued = time.monotonic()
        waiting = lambda why: self.progress and self.progress.stage(f"{STAGES.get(operation,'descarga')}: en espera de {why}",
                                                                    time.monotonic()-queued)
        reservation = self.resources.reserve(operation,waiting,day) if self.resources else contextlib.nullcontext()
        with tempfile.TemporaryDirectory(prefix='stage_', dir=temporary) as stage, reservation:
            # El tiempo en espera de RAM no cuenta para el límite ni para las métricas de la etapa.
            started = time.monotonic()
            # Se crea la peticion y se crea el archivo de resultado; el worker lo escribe al terminar.
            request, result = Path(stage)/'request.json', Path(stage)/'result.json'
            extra = {'scratch':str(Path(stage)/'scratch')} if self.resources else {}
            request.write_text(canonical({'operation':operation,'acolite':str(self.acolite),**extra,**arguments}))
            self.check_disk()
            # Ejecuta un proceso aislado de ACOLITE. usa (oceanos.worker.py)
            process = subprocess.Popen([sys.executable,'-m','oceanos.worker',str(request),str(result)],
                                       cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                       start_new_session=True,
                                       env=self.resources.environment() if self.resources else None)
            state = {}
            try:
                # Revisa el estado del proceso aislado anterior cada 2 segundos.
                while process.poll() is None:
                    if time.monotonic()-started > timeout:
                        raise TimeoutError('Tiempo máximo de etapa agotado')
                    self.check_disk()
                    self.watch(operation,process.pid,stage,started,arguments,state)
                    self.wait(2)
                    if self.resources and self.resources.stop.is_set():
                        raise KeyboardInterrupt
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
                raise StageError(operation, response.get('reason') or response.get('error','WorkerExit'),
                                 response.get('retry_after'))
            if self.resources and operation=='process':
                # LUT ya preparadas: los siguientes ACOLITE pueden correr a la vez si caben en RAM.
                self.resources.warm = True
            return response['result']

    def retry(self, function, process=None, scene=None):
        """Ejecuta `function` con los reintentos y esperas del perfil; relanza el último error.

        Credenciales, permisos o producto inexistente no se reintentan. Con la cuota del proveedor
        superada (429) se espera al menos QUOTA_WAIT segundos, o lo que indique Retry-After si no
        pasa de QUOTA_WAIT_MAX; si pide más, se deja de intentar. Las esperas son cortas a propósito:
        lo que no se consigue queda FALLIDO en el reporte y el siguiente run lo reintenta.
        """
        attempts = self.config['input']['transient_attempts_total']
        delays = self.config['input']['retry_wait_seconds']
        for attempt in range(attempts):
            try:
                return function()
            except Exception as error:
                code = reason(error)
                hint = getattr(error,'retry_after',None) or 0
                final = code in FINAL or (code == 'HTTP_429' and hint > QUOTA_WAIT_MAX)
                self.notify('INTENTO_FALLIDO', f'Descarga, intento {attempt+1} de {attempts}: {explain(code)}'
                            + (' (no se reintenta)' if final else ''), process, scene)
                if final or attempt+1 == attempts:
                    raise
                wait = delays[attempt]
                if code == 'HTTP_429':
                    wait = min(max(wait, QUOTA_WAIT, hint), QUOTA_WAIT_MAX)
                self.pause(wait)

    def search(self):
        """Consulta el proveedor del perfil, registra las escenas observadas y devuelve sus nombres."""
        # Sentinel-2 (SAFE) y OLCI (SEN3) desde CDSE; Landsat (TAR) desde USGS.
        provider = 'USGS' if self.config['family'] == 'landsat' else 'CDSE'
        attempts = self.config['input']['transient_attempts_total']
        for attempt in range(attempts):
            search = self.catalog.search_start(provider, self.config, attempt+1)
            try:
                # Proceso aislado de ACOLITE para la consulta.
                response = self.call('query', timeout=900, provider=provider, config=self.config)
                scenes = [self.catalog.upsert_scene(source) for source in response['sources']]
                for name, source in zip(scenes, response['sources']):
                    self.catalog.set_zones(name, zones_for(source, self.config))
                self.last_query = {'provider':provider,'count':len(response['sources']),
                                   **{k:v for k,v in response.items() if k!='sources'}}
                self.catalog.search_finish(search, 'OK', self.last_query)
                return list(dict.fromkeys(scenes))
            except Exception as error:
                self.catalog.search_finish(search, 'FALLIDA', error=reason(error))
                self.notify('BUSQUEDA_FALLIDA', f'{provider}, intento {attempt+1} de {attempts}: {explain(reason(error))}')
                if attempt+1 == attempts:
                    raise
                self.wait(self.config['input']['retry_wait_seconds'][attempt])

    def zones_pending(self, scene, source, force=False):
        """Zonas de la escena que faltan en el AOI: las que toca menos las ya terminadas en su adquisición."""
        touched = zones_for(source, self.config)
        if force:
            return touched
        row = self.catalog.db.execute('SELECT adquisicion FROM escenas WHERE escena=?', (scene,)).fetchone()
        done = self.catalog.zones_done(row['adquisicion'], self.config['aoi']['id']) if row else set()
        return [zone for zone in touched if zone not in done]

    def reuse_raw(self, scene, source, raw):
        """Mueve a `raw` el archivo ya descargado por un proceso fallido de la misma escena, si su SHA-256 coincide.

        Un proceso que falla después de descargar conserva sus temporales; así reintentar no repite
        la descarga. Devuelve el resultado de `acquire` o None si no hay nada reutilizable.
        """
        if not source.get('sha256'):
            return None
        for row in self.catalog.db.execute("SELECT id FROM procesos WHERE escena=? AND estado='FALLIDO' "
                                           "AND limpieza='APLAZADA' ORDER BY id DESC", (scene,)).fetchall():
            for archive in (self.catalog.storage/'temporary'/str(row['id'])).glob(source['product'].split('.')[0]+'.*'):
                if archive.suffix in ('.zip', '.tar') and file_hash(archive) == source['sha256']:
                    raw.mkdir(parents=True, exist_ok=True)
                    target = raw/archive.name
                    archive.replace(target)
                    self.notify('REUTILIZA_DESCARGA', f"Se usa la descarga del proceso {row['id']}; no se descarga otra vez",
                                scene=scene)
                    cleanup(self.catalog, row['id'], force=True)
                    return {'archive': str(target), 'source': source}
        return None

    def run(self, scene, source=None, force=False, zones=None):
        """Procesa una escena de principio a fin y devuelve el id del proceso.

        Descarga una vez, extrae y procesa cada zona pendiente (`zone`). Sin `force`, una escena
        cuya adquisición ya terminó todas sus zonas no se descarga: queda DISPONIBLE y devuelve
        None. `source` sustituye la fuente del catálogo (archivo local de `run --source`).
        """
        remote = source is None
        source = source or self.catalog.source(scene)
        if not eligible(source, self.config):
            raise ValueError('Escena fuera del perfil solicitado')
        # Las zonas de la escena quedan en el catálogo también si llega sin búsqueda (archivo local).
        self.catalog.set_zones(scene, zones_for(source, self.config))
        pending = zones or self.zones_pending(scene, source, force)
        if not pending:
            self.found = True
            state = self.catalog.db.execute('SELECT estado FROM escenas WHERE escena=?', (scene,)).fetchone()['estado']
            if state != 'PROCESADA':
                self.catalog.scene_state(scene, 'DISPONIBLE')
            self.notify('DISPONIBLE', 'No se descarga: la adquisición ya está procesada en sus zonas '
                                      '(use --force para reprocesar)', scene=scene)
            return None
        # Sin espacio para exportar no tiene sentido descargar: la escena queda FALLIDA para otro run.
        self.check_superimagen_budget()
        process = self.catalog.start(scene, 'LOCAL' if source.get('local') else 'DESCARGA', self.config)
        self.current_run = process
        raw = self.catalog.storage/'temporary'/str(process)
        self.metrics = []
        try:
            acquired = self.reuse_raw(scene, source, raw) if remote else None
            if not acquired:
                acquired = self.retry(lambda: self.call('acquire', source=source, raw=str(raw)), process, scene)
                self.record_download(process, acquired.get('archive'), acquired['source'])
            source = acquired['source']
            if remote:
                # Guarda el SHA-256 comprobado: identifica la misma fuente en el futuro y permite reutilizarla.
                self.catalog.upsert_scene(source, seen=False)
            extracted = self.call('extract', archive=acquired['archive'], raw=str(raw),
                                  available=self.config['budget']-self.used())
            results = {zone: self.zone(process, scene, source, extracted['input'], zone, raw) for zone in pending}
            self.catalog.finish(process, 'OK', 'TECNICA_OK', engine=self.engine, zones=results, metrics=self.metrics)
            disposition = cleanup(self.catalog, process)
            summary = ', '.join(f'{zone} {state}' for zone, state in results.items())
            self.notify('TECNICA_OK', f'Zonas: {summary}; temporales {disposition.lower()}; '
                                      'validación científica pendiente', process, scene)
            return process
        except BaseException as error:
            state = 'INTERRUMPIDO' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'FALLIDO'
            self.record_download(process)
            self.catalog.finish(process, state, error=reason(error), metrics=self.metrics)
            self.say(f'{state}: {explain(reason(error))}')
            if state == 'FALLIDO':
                try:
                    cleanup(self.catalog, process)
                except OSError:
                    self.notify('LIMPIEZA_FALLIDA', 'Temporales conservados', process, scene)
            raise

    def zone(self, process, scene, source, input_path, name, raw):
        """Procesa una zona de la escena y devuelve su resultado: OK, NUBOSA o SIN_DATOS.

        Nubes con la máscara del L1 → ACOLITE con la grilla de la zona → validación técnica →
        auxiliares reales → COG verificados en superimagen/escenas → linaje → borrado de L1R, L2R y
        L2W. Si algo falla, la excepción sube y los intermedios de la zona quedan en el temporal.
        """
        zone, family = self.config['zones'][name], self.config['family']
        info = source['identity']
        lineage = {'proceso': process, 'sensor': SENSOR_TAG[family], 'satelite': satellite(info),
                   'fecha': f"{info['date'][:4]}-{info['date'][4:6]}-{info['date'][6:8]}",
                   'instante_utc': scene_date(source), 'proveedor_id': source.get('id'), 'sha256': source.get('sha256'),
                   'checksum_proveedor': source.get('metadata', {}).get('Checksum'), 'baseline': info['baseline'],
                   'via_descarga': source.get('download_route') or source['provider'], 'acolite': self.engine,
                   'settings': zone['native']}
        clouds = self.call('clouds', input=input_path, family=family, zone=zone)
        if clouds:
            lineage.update(nubes_pct=clouds['nubes_pct'], nubes_origen=clouds['origen'], cobertura_pct=clouds['cobertura_pct'])
            outcome = self.cloud_outcome(clouds['cobertura_pct'], clouds['nubes_pct'])
            if outcome:
                return self.close_zone(scene, name, outcome, lineage)
        mask = mask_path(self.catalog.storage, name, family, self.config['resolution'])
        if not mask.is_file():
            raise StageError('export', 'SIN_MASCARA')
        work = raw/name
        work.mkdir(parents=True, exist_ok=True)
        settings = work/'settings.txt'
        settings.write_text('\n'.join(k+'='+str(v) for k, v in sorted(zone['native'].items()))+'\n')
        result = self.call('process', day=info['date'][:8], input=str(input_path), settings=str(settings),
                           output=str(work/'acolite'))
        files = result['files']
        validate(files, zone['grid'], self.config['products'])
        auxiliary = self.check_ancillary(result)
        self.check_superimagen_budget()
        folder = (Path('superimagen')/'escenas'/name/SENSOR_TAG[family]/
                  f"{lineage['fecha']}_{place(info)}")
        target = self.catalog.storage/folder
        mask_row = self.catalog.mask(name, SENSOR_TAG[family], self.config['resolution'])
        metadata = describe(source, name, family, self.engine, zone['native'], (mask_row or {}).get('capa', ''))
        exported = self.call('export', l2r=files['l2r'], l2w=files['l2w'], mask=str(mask), target=str(target),
                             grid=zone['grid'], metadata=metadata)
        verify(target, exported['files'])
        lineage.update(carpeta=str(folder), bytes=exported['bytes'], variables=sorted(exported['files']),
                       agua_vista_pct=exported['agua_vista_pct'], angulo_glint_deg=exported['angulo_glint_deg'],
                       auxiliares=auxiliary, mascara=(mask_row or {}).get('capa'))
        if not clouds:
            # Sin máscara de nubes en el L1 (OLCI): se mide con los flags de ACOLITE sobre el agua de la zona.
            lineage.update(nubes_pct=exported['nubes_flags_pct'], nubes_origen='l2_flags',
                           cobertura_pct=exported['agua_vista_pct'])
            outcome = self.cloud_outcome(exported['agua_vista_pct'], exported['nubes_flags_pct'])
            if outcome:
                shutil.rmtree(target)
                lineage.update(carpeta=None, bytes=None, variables=None)
                shutil.rmtree(work)
                return self.close_zone(scene, name, outcome, lineage)
        self.catalog.record_product(scene, name, self.config['aoi']['id'], estado='OK', **lineage)
        # Exportado, verificado y registrado: los NetCDF de la zona ya no hacen falta.
        shutil.rmtree(work)
        return 'OK'

    def cloud_outcome(self, coverage, clouds):
        """SIN_DATOS si la escena no cubre la zona, NUBOSA si supera el máximo de nubes; None si se procesa."""
        if not coverage:
            return 'SIN_DATOS'
        if clouds is not None and clouds > self.config['cloud_zone_max']:
            return 'NUBOSA'
        return None

    def close_zone(self, scene, name, outcome, lineage):
        """Registra una zona que no se exporta (NUBOSA o SIN_DATOS) y devuelve su resultado."""
        self.catalog.record_product(scene, name, self.config['aoi']['id'], estado=outcome, **lineage)
        self.notify(outcome, f"{name}: cobertura {lineage.get('cobertura_pct')} %, nubes {lineage.get('nubes_pct')} % "
                             f"(máximo {self.config['cloud_zone_max']} %)", lineage['proceso'], scene, echo=False)
        return outcome

    def check_ancillary(self, result):
        """Auxiliares usados por ACOLITE; StageError si quedaron los valores por defecto.

        Si la descarga de MERRA-2 falla, ACOLITE sigue en silencio con uoz, uwv y presión por
        defecto. Que los tres coincidan con el default no ocurre con datos reales: la escena queda
        FALLIDA y el próximo run la reintenta, en vez de pasar a la superimagen.
        """
        science = result['science_metadata']
        used = {key: science.get(key) for key in ('uoz', 'uwv', 'pressure', 'wind')}
        defaults = result.get('ancillary_defaults') or {}
        if defaults and all(used[key] is not None and float(used[key]) == float(defaults[key]) for key in defaults):
            raise StageError('process', 'AUXILIAR_POR_DEFECTO')
        return used

    def check_superimagen_budget(self):
        """StageError si exportar otra zona superaría el presupuesto de disco de la superimagen."""
        expected = self.catalog.product_bytes(SENSOR_TAG[self.config['family']]) or product_estimate(self.config)
        if superimagen_bytes(self.catalog.storage)+expected > self.config['superimagen_budget']:
            raise StageError('export', 'PRESUPUESTO_SUPERIMAGEN')

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
        """Procesa las escenas y devuelve el resumen del lote.

        Con `resources` y más de una escena las reparte entre varios hilos; si no, una a una.
        Cada escena queda PROCESADA, DISPONIBLE (sus zonas ya estaban terminadas) o FALLIDA (se
        reintenta en el próximo run). Devuelve {'runs': procesos creados, 'failed': escenas fallidas,
        'seconds': duración}.
        """
        started = time.monotonic()
        scenes = list(dict.fromkeys(scenes))
        workers = min(self.resources.workers,len(scenes)) if self.resources else 1
        if workers > 1:
            outcomes = self.parallel(scenes,force,workers)
        else:
            outcomes = [self.attempt(index,len(scenes),scene,force) for index, scene in enumerate(scenes,1)]
        if self.progress:
            self.progress.clear()
        return {'runs':[run for run, _, _ in outcomes if run],
                'failed':[scene for _, scene, failed in outcomes if failed],
                'seconds':round(time.monotonic()-started,3)}

    def attempt(self, index, total, scene, force=False):
        """Procesa una escena del lote, actualiza su estado en la cola y devuelve (proceso, escena, falló)."""
        if self.progress:
            row = self.catalog.db.execute('SELECT satelite, fecha_utc, tile FROM escenas WHERE escena=?',(scene,)).fetchone()
            self.progress.scene(index,total,f"{row['satelite']} {row['fecha_utc']} {row['tile']}")
        self.current_run, self.found = None, None
        failed = False
        try:
            self.run(scene,force=force)
            if not self.found:
                # Sin descarga porque sus zonas ya estaban terminadas, run() dejó la escena DISPONIBLE.
                self.catalog.scene_state(scene,'PROCESADA')
        except Exception:
            failed = True
            self.catalog.scene_state(scene,'FALLIDA')
        finally:
            if self.progress:
                self.progress.release()
        return self.current_run, scene, failed

    def parallel(self, scenes, force, workers):
        """Reparte las escenas entre `workers` hilos, cada uno con su copia del pipeline.

        Ctrl+C llega al hilo principal: se pide detener, cada hilo corta su proceso aislado
        (queda INTERRUMPIDO, como en secuencial) y se relanza la interrupción.
        """
        pending = list(enumerate(scenes,1))
        outcomes, lock = {}, threading.Lock()

        def lane():
            twin = self.clone()
            try:
                while not self.resources.stop.is_set():
                    with lock:
                        if not pending:
                            return
                        index, scene = pending.pop(0)
                    try:
                        outcomes[index] = twin.attempt(index,len(scenes),scene,force)
                    except KeyboardInterrupt:
                        return
                    except Exception:
                        # Fallo fuera de run() (p. ej. catálogo ocupado): la escena se reintenta en otro run.
                        outcomes[index] = (twin.current_run,scene,True)
            finally:
                twin.catalog.db.close()

        threads = [threading.Thread(target=lane,name=f'escena-{n}',daemon=True) for n in range(workers)]
        for thread in threads:
            thread.start()
        try:
            for thread in threads:
                while thread.is_alive():
                    thread.join(0.5)
        except KeyboardInterrupt:
            self.resources.stop.set()
            for thread in threads:
                thread.join()
            raise
        if self.resources.stop.is_set():
            raise KeyboardInterrupt
        return [outcomes[index] for index in sorted(outcomes)]


def cleanup(catalog, process, force=False):
    """Borra el temporal de un proceso (storage/temporary/<id>) y devuelve HECHA, APLAZADA o NO_APLICA.

    OK, INTERRUMPIDO u OMITIDO se borran: sus productos ya están en la superimagen o lo parcial no
    se reutiliza. FALLIDO se aplaza: conserva la descarga para que el próximo run no la repita
    (`Pipeline.reuse_raw`), que lo borra con `force` una vez movido el archivo.
    """
    row = catalog.process(int(process))
    process = row['id']
    if row['tipo'] == 'IMPORTADO' or row['legado']:
        # Legado e importados no tienen temporales propios y sus archivos nunca se borran.
        return 'NO_APLICA'
    if row['estado'] == 'FALLIDO' and not force:
        catalog.update(process, limpieza='APLAZADA')
        catalog.event('LIMPIEZA_APLAZADA', 'Se conserva la descarga para reintentar sin descargar otra vez',
                      process, row['escena'])
        return 'APLAZADA'
    target = catalog.storage/'temporary'/str(process)
    allowed = (catalog.storage/'temporary').resolve()
    if target.is_symlink() or not target.resolve().is_relative_to(allowed) or target.resolve() == allowed:
        raise ValueError('Ruta de limpieza fuera de la carpeta del proceso')
    try:
        if target.exists():
            shutil.rmtree(target)
    except OSError:
        catalog.update(process, limpieza='FALLIDA')
        catalog.event('LIMPIEZA_FALLIDA', 'No se pudo borrar temporary/'+str(process), process, row['escena'])
        raise
    catalog.update(process, limpieza='HECHA')
    catalog.event('LIMPIEZA_HECHA', 'Temporales borrados ('+row['estado'].lower()+')', process, row['escena'])
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
