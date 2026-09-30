"""Interfaz manual del MVP; ejecutar dentro del entorno ACOLITE de WSL."""
import argparse
import json
from pathlib import Path
from .catalog import Catalog
from .config import ROOT, canonical, exclusive, file_hash, profile
from .native import prepare, scene_identity, eligible
from .pipeline import Pipeline, cleanup


def parser():
    result = argparse.ArgumentParser(description='Pipeline OCEANOS: catálogo local y ACOLITE nativo')
    result.add_argument('--storage',type=Path,default=ROOT/'storage')
    result.add_argument('--acolite',type=Path,default=ROOT/'.work/acolite-audit')
    result.add_argument('--profile',type=Path,default=ROOT/'config/aoi/lapargera_v1/project.yaml')
    result.add_argument('--start',help='Inicio UTC incluido')
    result.add_argument('--end',help='Final UTC EXCLUIDO')
    result.add_argument('--products',help='Productos separados por coma; OC4 no soportado')
    commands = result.add_subparsers(dest='command',required=True)
    commands.add_parser('prepare',help='Aplicar el parche de metadata a la copia auditada')
    commands.add_parser('search',help='Consultar y guardar versiones sin descargar escenas')
    run = commands.add_parser('run',help='Consultar y procesar secuencialmente, o usar un archivo local')
    run.add_argument('--version',help='Versión ya registrada en el catálogo')
    run.add_argument('--source',type=Path,help='Archivo ZIP/TAR local recuperable')
    run.add_argument('--scene',help='Identificador nativo para la fuente local')
    run.add_argument('--force',action='store_true',help='Reprocesar aunque existan salidas técnicas verificadas')
    derive = commands.add_parser('derive',help='Regenerar L2W desde L1R sin descargar, repitiendo AC')
    derive.add_argument('--l1r',type=Path,required=True)
    derive.add_argument('--scene',required=True)
    commands.add_parser('status',help='Mostrar estados sin cargar ACOLITE')
    commands.add_parser('recover',help='Registrar interrupciones de ejecuciones abandonadas')
    clean = commands.add_parser('cleanup',help='Evaluar limpieza; conservar mientras falte aceptación científica')
    clean.add_argument('run')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        with exclusive(args.storage):
            if args.command=='prepare':
                print(canonical(prepare(args.acolite)))
                return 0
            catalog = Catalog(args.storage)
            try:
                if args.command=='status':
                    rows = catalog.db.execute('SELECT id,estado,validacion,limpieza,inicio FROM ejecuciones ORDER BY inicio').fetchall()
                    print(json.dumps([dict(r) for r in rows],indent=2,ensure_ascii=False))
                    return 0
                if args.command=='recover':
                    print('Ejecuciones interrumpidas registradas:',catalog.recover())
                    return 0
                if args.command=='cleanup':
                    print(cleanup(catalog,args.run))
                    return 0
                config = profile(args.profile,args.products.split(',') if args.products else None,args.start,args.end)
                pipeline = Pipeline(catalog,config,args.acolite)
                catalog.recover()
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
        print('Interrumpido; fuentes conservadas. Puede usar recover.')
        return 130
    except Exception as error:
        # No imprimir respuestas remotas ni excepciones con credenciales.
        print('OCEANOS no completó la operación:',type(error).__name__)
        print('Revise los eventos y resultados de etapa del catálogo.')
        return 1
