"""Proceso aislado: ACOLITE mantiene estado global entre llamadas y GDAL puede abortar el intérprete."""
import contextlib
import json
import os
import resource
import sys
from pathlib import Path
import netCDF4
from . import native
from .config import canonical, received_bytes

# Atributos del L2R que se guardan como metadata científica antes de borrarlo.
SCIENCE_KEYS = ('sensor', 'isodate', 'uoz', 'uwv', 'pressure', 'wind', 'sza', 'vza', 'raa', 'dsf_aot_estimate')
# Settings con los valores que ACOLITE usa cuando no consigue los auxiliares MERRA-2.
ANCILLARY_DEFAULTS = {'uoz': 'uoz_default', 'uwv': 'uwv_default', 'pressure': 'pressure_default'}


def run_acolite(ac, request):
    """ACOLITE de una zona: rutas de salida, metadata del L2R, settings y defaults de auxiliares."""
    files = native.process(ac, request['input'], request['settings'], request['output'])
    science = {}
    if not files.get('empty'):
        # Sin datos sobre la zona no hay L2R: la zona queda SIN_DATOS y no hay metadata que leer.
        with netCDF4.Dataset(files['l2r']) as dataset:
            science = {key: getattr(dataset, key) for key in dataset.ncattrs()
                       if key.startswith(('ac_', 'ancillary', 'lut', 'rsr')) or key in SCIENCE_KEYS}
    run = ac.settings['run']
    overrides = {k: v for k, v in ac.settings['user'].items() if k not in ('inputfile', 'output', 'runid')}
    return {'files': files, 'science_metadata': science, 'settings': overrides,
            'ancillary_defaults': {key: run.get(name) for key, name in ANCILLARY_DEFAULTS.items()},
            'environment': {'python': sys.version.split()[0], 'acolite': ac.version}}


def execute(operation, request):
    """Ejecuta una operación; carga ACOLITE solo si la usa."""
    if operation == 'clouds':
        from .escenas import cloud_fraction
        return cloud_fraction(request['input'], request['family'], request['zone'])
    ac = native.load(request['acolite'])
    if request.get('scratch'):
        # En paralelo cada etapa usa su scratch: ACOLITE descarga auxiliares ahí con el nombre final.
        Path(request['scratch']).mkdir(parents=True, exist_ok=True)
        ac.config['scratch_dir'] = request['scratch']
    if operation == 'query':
        return native.query(ac, request['provider'], request['config'])
    if operation == 'acquire':
        return native.acquire(ac, request['source'], request['raw'])
    if operation == 'extract':
        return native.extract(ac, request['archive'], request['raw'], request['available'])
    if operation == 'process':
        return run_acolite(ac, request)
    if operation == 'export':
        from .escenas import export
        return export(ac, request['l2r'], request['l2w'], request['mask'], request['target'], request['grid'],
                      request['metadata'])
    raise ValueError('Operación desconocida')


def main():
    """Lee request.json, ejecuta la operación pedida y escribe result.json."""
    request_path, result_path = map(Path, sys.argv[1:3])
    request = json.loads(request_path.read_text())
    try:
        operation = request['operation']
        # Línea base para que el proceso principal mida los bytes descargados (barra de progreso).
        baseline = received_bytes()
        if baseline is not None:
            (request_path.parent/'baseline').write_text(str(baseline))
        # Las APIs de autenticación nativas pueden imprimir datos: no persistir stdout de red.
        with open(os.devnull, 'w') as sink:
            target = contextlib.nullcontext() if operation == 'process' else contextlib.redirect_stdout(sink)
            with target:
                result = execute(operation, request)
        result_path.write_text(json.dumps({'ok': True, 'result': result,
                                           'peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},
                                          default=str))
    except Exception as error:
        # Nunca serializar mensajes HTTP, tokens ni cuerpos de autenticación: solo tipo y motivo corto.
        result_path.write_text(canonical({'ok': False, 'error': type(error).__name__,
                                          'reason': getattr(error, 'reason', None),
                                          'retry_after': getattr(error, 'retry_after', None)}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
