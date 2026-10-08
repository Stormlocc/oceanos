"""Sincroniza en el catálogo L1R/L2W copiados a mano, guiándose solo por el nombre del archivo."""
import shutil
from pathlib import Path
from .native import output_identity

RESERVED = ('catalog', 'temporary')


def scene_for(catalog, identity):
    """Escena del proveedor con la misma adquisición o, si no hay, una escena LOCAL creada desde el nombre."""
    row = catalog.db.execute("SELECT escena FROM escenas WHERE adquisicion=? AND proveedor IN ('CDSE','USGS') "
                             "ORDER BY vista DESC", (identity['acquisition_key'],)).fetchone()
    if row:
        return row['escena']
    name = identity['acquisition_key'].replace(':', '_')
    exists = catalog.db.execute('SELECT 1 FROM escenas WHERE escena=?', (name,)).fetchone()
    if not exists:
        info = {k: v for k, v in identity.items() if k not in ('region', 'level')}
        catalog.upsert_scene({'provider': 'LOCAL', 'product': name, 'format': 'ACOLITE', 'identity': info,
                              'metadata': {'identity_origin': 'nombre_de_salida_acolite'}}, seen=False)
    return name


def adopt(catalog, container, target):
    """Renombra una carpeta de storage/runs a su nombre legible y saca los NetCDF de `output/`."""
    target = catalog.storage/target
    if container != target:
        if target.exists():
            raise ValueError(f'Ya existe {target.relative_to(catalog.storage)}')
        container.rename(target)
    for path in sorted(target.rglob('*.nc')):
        if path.parent != target:
            path.rename(target/path.name)
    for folder in sorted((p for p in target.rglob('*') if p.is_dir()), reverse=True):
        if not any(folder.iterdir()):
            folder.rmdir()
    return target


def sync(catalog, folder, hashed=False):
    """Registra en el catálogo los L1R/L2W de `folder` (dentro de storage) que aún no estén.

    No abre los NetCDF: escena, fecha, tile y región salen del nombre. Cada par L1R/L2W queda
    como un proceso IMPORTADO (validación SIN_VERIFICAR, SHA-256 solo con `hashed`) y la escena
    como IMPORTADA: indica que la adquisición ya está disponible para que `run` no la descargue,
    pero nunca se reutiliza como L1R padre ni se borra. En `storage/runs` cada subcarpeta se
    adopta con nombre legible (0001_S2B_2026-01-06). Es idempotente: lo registrado se omite, lo
    que desapareció se marca FALTAN y lo que reaparece con el mismo tamaño vuelve a PRESENTES.
    """
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError('Carpeta de importación inexistente')
    if not folder.is_relative_to(catalog.storage) or folder == catalog.storage:
        raise ValueError('La carpeta de importación debe estar dentro de storage')
    relative = folder.relative_to(catalog.storage)
    if relative.parts[0] in RESERVED:
        raise ValueError('La carpeta de importación no puede estar en '+', '.join(RESERVED))
    runs = (catalog.storage/'runs').resolve()
    known = {}
    for row in catalog.db.execute('SELECT * FROM procesos').fetchall():
        for kind in ('L1R', 'L2W'):
            if row[kind.lower()]:
                known[row[kind.lower()]] = (dict(row), kind)
    report = {'carpeta': str(relative), 'importados': [], 'ya_registrados': 0, 'reaparecidos': [],
              'desaparecidos': [], 'no_reconocidos': [], 'duplicados': []}
    groups, checked = {}, set()
    for path in sorted(folder.rglob('*.nc')):
        name = str(path.relative_to(catalog.storage))
        if name in known:
            row, _ = known[name]
            report['ya_registrados'] += 1
            # Un proceso con archivos faltantes vuelve a PRESENTES si están todos con su tamaño.
            if row['archivos'] == 'FALTAN' and row['id'] not in checked:
                checked.add(row['id'])
                back = all((catalog.storage/row[k]).is_file() and (catalog.storage/row[k]).stat().st_size == row[f'{k}_bytes']
                           for k in ('l1r', 'l2w') if row[k])
                if back:
                    catalog.update(row['id'], archivos='PRESENTES')
                    report['reaparecidos'].append(f"proceso {row['id']} ({row['carpeta']})")
            continue
        try:
            identity = output_identity(path.name)
        except ValueError:
            report['no_reconocidos'].append(name)
            continue
        # En storage/runs cada subcarpeta es un proceso; fuera de runs se agrupa por adquisición y región.
        container = runs/path.relative_to(runs).parts[0] if path.is_relative_to(runs) else None
        group = groups.setdefault((identity['acquisition_key'], identity['region'], container),
                                  {'identity': identity, 'files': {}})
        if identity['level'] in group['files']:
            report['duplicados'].append(name)
            continue
        group['files'][identity['level']] = path
    # Orden cronológico: los procesos y carpetas adoptados quedan numerados por fecha de adquisición.
    for (key, region, container), group in sorted(groups.items(), key=lambda item: (item[1]['identity']['date'], item[0][0])):
        scene = scene_for(catalog, group['identity'])
        files = group['files']
        carpeta = None if container else str(next(iter(files.values())).parent.relative_to(catalog.storage))
        # Un L1R que llega después de su L2W (o al revés) completa el proceso importado existente.
        existing = carpeta and catalog.db.execute("SELECT id FROM procesos WHERE tipo='IMPORTADO' AND escena=? "
                                                  "AND carpeta=? AND aoi IS ?", (scene, carpeta, region)).fetchone()
        process = existing['id'] if existing else catalog.start(scene, 'IMPORTADO', {'aoi': {'id': region}})
        if container:
            target = adopt(catalog, container, catalog.process(process)['carpeta'])
            files = {level: target/path.name for level, path in files.items()}
            carpeta = str(target.relative_to(catalog.storage))
        for level, path in sorted(files.items()):
            catalog.artifact(process, level, path, hashed=hashed)
            report['importados'].append({'archivo': str(path.relative_to(catalog.storage)), 'tipo': level,
                                         'escena': scene, 'proceso': process})
        catalog.update(process, carpeta=carpeta, limpieza='NO_APLICA')
        if not existing:
            catalog.finish(process, 'IMPORTADO', 'SIN_VERIFICAR')
        catalog.scene_state(scene, 'IMPORTADA')
        catalog.event('IMPORTADO', f'{len(files)} archivo(s) en {carpeta} ({key}, región {region})', process, scene)
    # Registrados dentro de esta carpeta que ya no están en disco.
    for name, (row, kind) in known.items():
        if Path(name).is_relative_to(relative) and row['archivos'] == 'PRESENTES' and not (catalog.storage/name).is_file():
            catalog.missing(row['id'])
            report['desaparecidos'].append(name)
    return report
