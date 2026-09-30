"""Catálogo SQLite: snapshots inmutables y estados operativos separados."""
import json
import sqlite3
import uuid
from pathlib import Path
from .config import canonical, digest, file_hash, now

SCHEMA = '''
CREATE TABLE IF NOT EXISTS consultas (
 id TEXT PRIMARY KEY, batch_id TEXT, parent_id TEXT, proveedor TEXT,
 filtros TEXT, estado TEXT, completitud TEXT, inicio TEXT, fin TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS versiones_producto (
 id TEXT PRIMARY KEY, proveedor TEXT, producto TEXT, metadata_hash TEXT,
 contenido TEXT, snapshot TEXT, inicio TEXT,
 UNIQUE(proveedor, producto, metadata_hash));
CREATE TABLE IF NOT EXISTS observaciones (
 consulta_id TEXT REFERENCES consultas(id), version_id TEXT REFERENCES versiones_producto(id),
 ocurrencias INTEGER DEFAULT 1, PRIMARY KEY(consulta_id, version_id));
CREATE TABLE IF NOT EXISTS ejecuciones (
 id TEXT PRIMARY KEY, version_id TEXT REFERENCES versiones_producto(id),
 processing_key TEXT, correction_key TEXT, parent_artifact_id TEXT,
 configuracion TEXT, estado TEXT, validacion TEXT, limpieza TEXT,
 inicio TEXT, fin TEXT, error TEXT, provenance_hash TEXT, resumen TEXT DEFAULT '{}');
CREATE TABLE IF NOT EXISTS artefactos (
 id TEXT PRIMARY KEY, run_id TEXT REFERENCES ejecuciones(id), tipo TEXT,
 ruta TEXT, bytes INTEGER, sha256 TEXT, metadata TEXT,
 validacion TEXT, disponibilidad TEXT);
CREATE TABLE IF NOT EXISTS eventos (
 id INTEGER PRIMARY KEY, run_id TEXT, consulta_id TEXT, instante TEXT,
 tipo TEXT, detalles TEXT);
CREATE INDEX IF NOT EXISTS trabajo ON ejecuciones(processing_key,estado);
CREATE INDEX IF NOT EXISTS correccion ON ejecuciones(correction_key,estado);
CREATE INDEX IF NOT EXISTS salida ON artefactos(run_id,tipo);

'''


class Catalog:
    def __init__(self, storage):
        self.storage = Path(storage).resolve()
        folder = self.storage/'catalog'
        folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(folder/'catalog.sqlite')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, 2):
            raise ValueError('Versión de catálogo no soportada')
        if version == 1:
            with self.db:
                self.db.execute("ALTER TABLE ejecuciones ADD COLUMN resumen TEXT DEFAULT '{}'")
                self.db.execute('PRAGMA user_version=2')
        self.db.executescript(SCHEMA)
        self.db.execute('PRAGMA user_version=2')

    def event(self, kind, details, run=None, query=None):
        with self.db:
            self.db.execute('INSERT INTO eventos(run_id,consulta_id,instante,tipo,detalles) VALUES(?,?,?,?,?)',
                            (run, query, now(), kind, canonical(details)))

    def query(self, provider, filters, batch=None, parent=None):
        key = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO consultas VALUES(?,?,?,?,?,?,?,?,?,?)',
                            (key, batch, parent, provider, canonical(filters), 'STARTED', 'UNKNOWN', now(), None, None))
        return key

    def finish_query(self, key, state, completeness='UNKNOWN', error=None):
        with self.db:
            self.db.execute('UPDATE consultas SET estado=?,completitud=?,fin=?,error=? WHERE id=?',
                            (state, completeness, now(), error, key))

    def observe(self, query, source):
        # El adaptador solo entrega metadata seleccionada sin URLs de sesión.
        metadata_hash = digest(source)
        provider, product = source['provider'], source['product']
        row = self.db.execute('SELECT id FROM versiones_producto WHERE proveedor=? AND producto=? AND metadata_hash=?',
                              (provider, product, metadata_hash)).fetchone()
        key = row['id'] if row else uuid.uuid4().hex
        with self.db:
            if not row:
                self.db.execute('INSERT INTO versiones_producto VALUES(?,?,?,?,?,?,?)',
                                (key, provider, product, metadata_hash, source.get('sha256'), canonical(source), now()))
            self.db.execute('INSERT INTO observaciones VALUES(?,?,1) ON CONFLICT(consulta_id,version_id) DO UPDATE SET ocurrencias=ocurrencias+1',
                            (query, key))
        return key

    def verified_source(self, source):
        """Reutilizar SHA local solo con checksum comparable o SHA local ya comprobado."""
        if source.get('sha256'):
            return source
        checksums = source.get('metadata', {}).get('Checksum')
        if not checksums:
            return source
        comparable = lambda values: sorted((v['Algorithm'].lower(), v['Value'].lower()) for v in values)
        rows = self.db.execute('SELECT snapshot FROM versiones_producto WHERE proveedor=? AND producto=? AND contenido IS NOT NULL ORDER BY inicio DESC',
                               (source['provider'],source['product'])).fetchall()
        for row in rows:
            previous = json.loads(row['snapshot'])
            old = previous.get('metadata', {}).get('Checksum')
            if previous['format'] == source['format'] and old and comparable(old) == comparable(checksums):
                return {**source,'sha256':previous['sha256']}
        return source

    def source(self, version):
        row = self.db.execute('SELECT snapshot FROM versiones_producto WHERE id=?', (version,)).fetchone()
        if not row:
            raise ValueError('Versión no encontrada')
        return json.loads(row['snapshot'])

    def start(self, version, config, processing_key, correction_key, parent=None):
        key = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO ejecuciones(id,version_id,processing_key,correction_key,parent_artifact_id,configuracion,estado,validacion,limpieza,inicio,fin,error,provenance_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                            (key, version, processing_key, correction_key, parent, canonical(config),
                             'STARTED', 'PENDING', 'RETAINED', now(), None, None, None))
            self.event('STARTED', {}, run=key)
        return key

    def finish(self, run, state, validation='PENDING', error=None, provenance=None, summary=None):
        with self.db:
            self.db.execute('UPDATE ejecuciones SET estado=?,validacion=?,fin=?,error=?,provenance_hash=?,resumen=? WHERE id=?',
                            (state, validation, now(), error, provenance, canonical(summary or {}), run))
            self.event(state, {'validacion': validation, 'error': error}, run=run)

    def artifact(self, run, kind, path, metadata, validation='TECHNICAL_PASSED'):
        path = Path(path).resolve()
        relative = path.relative_to(self.storage)
        key = uuid.uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO artefactos VALUES(?,?,?,?,?,?,?,?,?)',
                            (key, run, kind, str(relative), path.stat().st_size,
                             file_hash(path), canonical(metadata), validation, 'PRESENT'))
        return key

    def available(self, artifact):
        path = (self.storage/artifact['ruta']).resolve()
        ok = path.is_relative_to(self.storage) and path.is_file() and path.stat().st_size == artifact['bytes']
        ok = ok and file_hash(path) == artifact['sha256']
        if not ok:
            with self.db:
                self.db.execute("UPDATE artefactos SET disponibilidad='MISSING' WHERE id=?", (artifact['id'],))
        return ok

    def reusable(self, key, correction=False):
        column = 'correction_key' if correction else 'processing_key'
        kind = 'L1R' if correction else 'L2W'
        rows = self.db.execute(f'''SELECT a.* FROM artefactos a JOIN ejecuciones e ON e.id=a.run_id
            WHERE e.{column}=? AND e.estado='SUCCEEDED' AND a.tipo=?
            AND a.validacion='TECHNICAL_PASSED' AND a.disponibilidad='PRESENT' ORDER BY e.inicio DESC''', (key, kind))
        for row in rows.fetchall():
            if self.available(row):
                return dict(row)
        return None

    def recover(self):
        # Solo llamar bajo el bloqueo exclusivo; un archivo huérfano no se aprueba.
        with self.db:
            runs = self.db.execute("SELECT id FROM ejecuciones WHERE estado='STARTED'").fetchall()
            for row in runs:
                self.finish(row['id'], 'INTERRUPTED', error='Interrupción detectada al recuperar')
            self.db.execute("UPDATE consultas SET estado='INTERRUPTED',fin=? WHERE estado='STARTED'", (now(),))
        return len(runs)

