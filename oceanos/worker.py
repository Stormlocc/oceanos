"""Proceso aislado: ACOLITE puede mantener estado global entre llamadas."""
import contextlib
import json
import os
import resource
import sys
from pathlib import Path
import netCDF4
from . import native
from .config import canonical


def main():
    """Lee request.json, ejecuta la operación pedida y escribe result.json."""
    request_path, result_path = map(Path, sys.argv[1:3])
    request = json.loads(request_path.read_text())
    try:
        operation = request['operation']
        ac = native.load(request['acolite'])
        # Las APIs de autenticación nativas pueden imprimir datos: no persistir stdout de red.
        with open(os.devnull, 'w') as sink:
            target = contextlib.nullcontext() if operation == 'process' else contextlib.redirect_stdout(sink)
            with target:
                if operation == 'query':
                    result = native.query(ac, request['provider'], request['config'])
                elif operation == 'acquire':
                    result = native.acquire(ac, request['source'], request['raw'])
                elif operation == 'extract':
                    result = native.extract(ac, request['archive'], request['raw'], request['available'])
                elif operation == 'process':
                    result = native.process(ac, request['input'], request['settings'], request['output'], request.get('derive',False))
                    # Seleccionar metadata científica antes de eliminar el L2R temporal.
                    with netCDF4.Dataset(result['l2r']) as dataset:
                        science = {key:getattr(dataset,key) for key in dataset.ncattrs()
                                   if key.startswith(('ac_', 'ancillary', 'lut', 'rsr'))
                                   or key in ('sensor','isodate','uoz','uwv','pressure','wind','sza','vza','raa')}
                    overrides = ac.settings['user']
                    overrides = {k:v for k,v in overrides.items() if k not in ('inputfile','output','runid')}
                    result = {'files':result, 'science_metadata':science, 'settings':overrides,
                              'environment':{'python':sys.version.split()[0],'acolite':ac.version}}
                else:
                    raise ValueError('Operación desconocida')
        result_path.write_text(json.dumps({'ok':True,'result':result,'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024},default=str))
    except Exception as error:
        # Nunca serializar mensajes HTTP, tokens ni cuerpos de autenticación.
        result_path.write_text(canonical({'ok':False,'error':type(error).__name__}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
