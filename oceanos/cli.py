"""Interfaz manual del MVP; ejecutar dentro del entorno ACOLITE de WSL."""
import argparse
import json
from pathlib import Path
from .catalog import Catalog
from .config import ROOT, ACOLITE, canonical, exclusive, file_hash, profile
from .native import prepare, scene_identity, eligible
from .pipeline import Pipeline, cleanup, recover


def parser():
    """Define los argumentos globales y los subcomandos del CLI."""
    result = argparse.ArgumentParser(description='Pipeline OCEANOS: catálogo local y ACOLITE nativo')
    result.add_argument('--storage',type=Path,default=ROOT/'storage')
    result.add_argument('--acolite',type=Path,default=ACOLITE)
    result.add_argument('--profile',type=Path,default=ROOT/'config/aoi/lapargera_v1/project.yaml')
    result.add_argument('--start',help='Inicio UTC incluido')
    result.add_argument('--end',help='Final UTC EXCLUIDO')
    result.add_argument('--products',help='Productos separados por coma; OC4 no soportado')
    commands = result.add_subparsers(dest='command',required=True)
    commands.add_parser('prepare',help='Verificar la revisión de ACOLITE y aplicar el parche de catálogo')
    commands.add_parser('search',help='Consultar y guardar versiones sin descargar escenas')
    run = commands.add_parser('run',help='Consultar y procesar secuencialmente, o usar un archivo local')
    run.add_argument('--version',help='Versión ya registrada en el catálogo')
    run.add_argument('--source',type=Path,help='Archivo ZIP/TAR local recuperable')
    run.add_argument('--scene',help='Identificador nativo para la fuente local')
    run.add_argument('--force',action='store_true',help='Reprocesar aunque existan salidas técnicas verificadas')
    derive = commands.add_parser('derive',help='Regenerar L2W desde L1R sin descargar, repitiendo AC')
    derive.add_argument('--l1r',type=Path,required=True)
    derive.add_argument('--scene',required=True)
    status = commands.add_parser('status',help='Mostrar ejecuciones sin cargar ACOLITE')
    status.add_argument('run',nargs='?',help='Id o prefijo: detalle con artefactos, métricas y eventos')
    status.add_argument('--estado',choices=['STARTED','SUCCEEDED','SKIPPED','FAILED','INTERRUPTED'])
    status.add_argument('--ultimas',type=int,metavar='N',help='Solo las N ejecuciones más recientes')
    commands.add_parser('recover',help='Registrar interrupciones y limpiar lo parcial de ejecuciones interrumpidas')
    clean = commands.add_parser('cleanup',help='Evaluar limpieza tras QA técnico, reintentos agotados de fuente recuperable o interrupción')
    clean.add_argument('run')
    return result


def main(argv=None):
    """Ejecuta un subcomando bajo el bloqueo exclusivo del catálogo y devuelve el código de salida."""
    args = parser().parse_args(argv)
    try:
        with exclusive(args.storage):
            if args.command=='prepare':
                print(canonical(prepare(args.acolite)))
                return 0
            catalog = Catalog(args.storage)
            try:
                if args.command=='status':
                    try:
                        result = catalog.run_detail(args.run) if args.run else catalog.runs(args.estado,args.ultimas)
                    except ValueError as error:
                        # Mensajes locales del catálogo, sin datos remotos.
                        print(error)
                        return 1
                    print(json.dumps(result,indent=2,ensure_ascii=False))
                    return 0
                if args.command=='recover':
                    result = recover(catalog)
                    print(json.dumps(result,indent=2,ensure_ascii=False))
                    return 1 if result['limpieza_fallida'] else 0
                if args.command=='cleanup':
                    print(cleanup(catalog,args.run))
                    return 0
                # Carga el AOI/perfil 
                config = profile(args.profile, args.products.split(',') if args.products else None,args.start,args.end)
                pipeline = Pipeline(catalog, config, args.acolite)
                recovered = recover(catalog)
                if recovered['limpiadas'] or recovered['limpieza_fallida']:
                    print('Recuperación:',json.dumps(recovered,ensure_ascii=False))
                # DERIVE o RUN con fuente local requieren archivo existente.
                if args.command=='derive' or getattr(args,'source',None):
                    path = args.l1r if args.command=='derive' else args.source
                    if not getattr(args,'scene',None) or not path.is_file():
                        raise ValueError('Se requiere archivo existente y --scene')
                    source = {'provider':'LOCAL','product':args.scene,
                              'format':'L1R' if args.command=='derive' else ('SAFE' if config['family']=='sentinel2' else 'TAR'),
                              'local':str(path.resolve()),'sha256':file_hash(path),
                              'identity':scene_identity(args.scene),'metadata':{'identity_origin':'nombre_del_producto'}}
                    if not eligible(source,config):
                        raise ValueError('Escena fuera del sensor, intervalo o tile/path/row del perfil')
                    query = catalog.query('LOCAL',{'path':str(path.resolve())})
                    version = catalog.observe(query,source)
                    catalog.finish_query(query,'SUCCEEDED','COMPLETE')
                    pipeline.run(version,local_l1r=path if args.command=='derive' else None,force=getattr(args,'force',False))
                # SEARCH o RUN sin fuente local.
                elif args.command=='search':
                    print(canonical({'versions':pipeline.search()}))
                elif args.version:
                    pipeline.run(args.version,force=args.force)
                else:
                    failed = pipeline.batch(pipeline.search(),force=args.force)
                    return 1 if failed else 0
                return 0
            finally:
                catalog.db.close()
    except KeyboardInterrupt:
        print('Interrumpido; lo parcial se limpiará con recover (automático al iniciar search/run/derive).')
        return 130
    except Exception as error:
        # No imprimir respuestas remotas ni excepciones con credenciales.
        print('OCEANOS no completó la operación:',type(error).__name__)
        print('Revise los eventos y resultados de etapa del catálogo.')
        return 1
