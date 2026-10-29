"""Checksummed workspace archives; model artifacts are never deserialized here."""
import hashlib
import json
from contextlib import closing
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import tempfile
from uuid import uuid4
import zipfile
from datetime import datetime, timezone
from importlib.metadata import version

from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url

from cvti.db import make_engine, session_factory
from cvti.models import DatasetVersion, Experiment
from cvti.provenance import verify_version
from cvti.workspace_lock import workspace_lock

MAX_ARCHIVE_BYTES = 10 * 1024**3


def _sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def _pg(tool, database_url, *args):
    url = make_url(database_url)
    env = dict(os.environ)
    for key, value in {'PGHOST': url.host or 'localhost', 'PGPORT': str(url.port or 5432),
                       'PGUSER': url.username or '', 'PGPASSWORD': url.password or '',
                       'PGDATABASE': url.database or '', 'PGOPTIONS': url.query.get('options', '')}.items():
        env[key] = value
    try:
        result = subprocess.run([tool, *args], env=env, capture_output=True, text=True, timeout=300)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f'{tool} is unavailable or timed out; install matching PostgreSQL client tools') from exc
    if result.returncode:
        # Do not print credentials or server diagnostics containing connection strings.
        raise RuntimeError(f'{tool} failed (exit {result.returncode}); verify server/client versions, permissions and connectivity')


def inspect_backup(archive):
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or 'manifest.json' not in names:
            raise ValueError('Invalid backup: duplicate members or missing manifest')
        total = 0
        for info in bundle.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or '..' in path.parts or '\\' in info.filename or ':' in info.filename or info.is_dir():
                raise ValueError('Invalid backup member path')
            total += info.file_size
        if total > MAX_ARCHIVE_BYTES or bundle.getinfo('manifest.json').file_size > 10_000_000:
            raise ValueError('Backup exceeds supported size')
        manifest = json.loads(bundle.read('manifest.json'))
        if manifest.get('format_version') != 1 or manifest.get('backend') not in {'sqlite', 'postgresql'}:
            raise ValueError('Unsupported backup format')
        if set(names) != set(manifest['files']) | {'manifest.json'}:
            raise ValueError('Backup manifest does not match archive members')
        for name, expected in manifest['files'].items():
            with bundle.open(name) as handle:
                actual = hashlib.file_digest(handle, 'sha256').hexdigest()
            if actual != expected['sha256'] or bundle.getinfo(name).file_size != expected['bytes']:
                raise ValueError(f'Backup checksum failed: {name}')
        for name in manifest.get('artifacts', {}).values():
            if name not in manifest['files']:
                raise ValueError('Model artifact missing from manifest')
        if manifest['database_file'] not in manifest['files']:
            raise ValueError('Database missing from manifest')
        return manifest


def create_backup(database_url, artifact_dir, output, *, services_stopped=False):
    if not services_stopped:
        raise ValueError('Stop API, dashboard and writers, then pass --services-stopped')
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Backup output already exists')
    url = make_url(database_url)
    engine = make_engine(database_url)
    with workspace_lock(database_url, artifact_dir), tempfile.TemporaryDirectory() as temporary:
        stage = Path(temporary)
        try:
            with session_factory(engine)() as session:
                for dataset in session.scalars(select(DatasetVersion)):
                    verify_version(dataset)
                runs = session.scalars(select(Experiment)).all()
                revision = session.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                artifacts = {}
                for run in runs:
                    from cvti.training_provenance import verify_artifact
                    source = verify_artifact(run)
                    if not source.is_file():
                        raise ValueError(f'Model artifact missing for experiment {run.id}; repair before backing up')
                    name = f'artifacts/experiment-{run.id}.joblib'
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
                    artifacts[str(run.id)] = name
            if url.get_backend_name() == 'sqlite':
                if url.database in {None, ':memory:'}:
                    raise ValueError('Backup needs a file-backed SQLite database')
                database_file = 'database.sqlite'
                # sqlite3's own context manager commits/rolls back but does not
                # close handles. Windows cannot clean up the snapshot while open.
                with closing(sqlite3.connect(str(Path(url.database).resolve()))) as source, closing(sqlite3.connect(stage / database_file)) as dest:
                    with dest:
                        source.backup(dest)
            else:
                database_file = 'database.dump'
                _pg('pg_dump', database_url, '--format=custom', '--no-owner', '--no-privileges', '--file', str(stage / database_file))
            source_dir = Path(url.database).resolve().parent if url.get_backend_name() == 'sqlite' else Path(artifact_dir).resolve().parent
            # Retained inputs/exports, never .env, arbitrary sibling files or old archives.
            runtime_directories = {'runtime', 'ollama', 'assistant-training', 'workspaces', 'backups'}
            for directory, folders, names in os.walk(source_dir, followlinks=False):
                current = Path(directory)
                folders[:] = [name for name in folders if not name.startswith('.')
                              and not (current / name).is_symlink()
                              and not (current == source_dir and name in runtime_directories)]
                for name in names:
                    path = current / name
                    if not name.startswith('.') and not path.is_symlink() and path.suffix.lower() in {'.json', '.csv', '.md'}:
                        destination = stage / 'sources' / path.relative_to(source_dir)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(path, destination)
            manifest = {'format_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                        'application_version': version('cvti-mvp'), 'schema_revision': revision,
                        'backend': url.get_backend_name(), 'database_file': database_file,
                        'artifacts': artifacts, 'files': {}}
            for path in sorted(stage.rglob('*')):
                if path.is_file():
                    manifest['files'][path.relative_to(stage).as_posix()] = {'sha256': _sha(path), 'bytes': path.stat().st_size}
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2))
            output.parent.mkdir(parents=True, exist_ok=True)
            temporary_archive = output.with_name(output.name + '.' + uuid4().hex + '.tmp')
            try:
                with zipfile.ZipFile(temporary_archive, 'x', zipfile.ZIP_DEFLATED) as bundle:
                    for path in sorted(stage.rglob('*')):
                        if path.is_file():
                            bundle.write(path, path.relative_to(stage).as_posix())
                inspect_backup(temporary_archive)
                # Exclusive final creation prevents accidental overwrite of another backup.
                with temporary_archive.open('rb') as source, output.open('xb') as dest:
                    shutil.copyfileobj(source, dest)
            finally:
                temporary_archive.unlink(missing_ok=True)
            return {'output': str(output), 'manifest': manifest}
        finally:
            engine.dispose()


def restore_backup(archive, destination, *, database_url=None, replace=False, services_stopped=False):
    if not services_stopped:
        raise ValueError('Stop all writers, then pass --services-stopped')
    manifest = inspect_backup(archive)
    destination = Path(destination).resolve()
    if destination.exists() and not replace:
        raise ValueError('Destination exists; choose a new directory or pass --replace')
    if destination == Path.cwd().resolve() or Path.cwd().resolve().is_relative_to(destination):
        raise ValueError('Restore into a separate workspace directory, not over the source repository')
    if manifest['backend'] == 'postgresql' and not database_url:
        raise ValueError('PostgreSQL restore requires --database-url pointing to a new empty database')
    if database_url and make_url(database_url).get_backend_name() != manifest['backend']:
        raise ValueError('Restore backend must match the backup')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        stage = Path(temporary)
        with zipfile.ZipFile(archive) as bundle:
            for name in manifest['files']:
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(name) as source, path.open('xb') as dest:
                    shutil.copyfileobj(source, dest)
        target_url = database_url or f'sqlite:///{stage / "database.sqlite"}'
        engine = make_engine(target_url)
        try:
            if manifest['backend'] == 'postgresql':
                if inspect(engine).get_table_names():
                    raise ValueError('PostgreSQL destination must be empty; restore never drops an existing database')
                _pg('pg_restore', target_url, '--exit-on-error', '--single-transaction', '--no-owner', '--no-privileges',
                    '--dbname', make_url(target_url).database, str(stage / manifest['database_file']))
            with engine.begin() as conn:
                revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
                if revision != manifest['schema_revision']:
                    raise ValueError('Restored schema does not match backup manifest')
                for identifier, name in manifest['artifacts'].items():
                    conn.execute(text('UPDATE experiments SET artifact_path=:path WHERE id=:id'),
                                 {'path': str(destination / name), 'id': int(identifier)})
            with session_factory(engine)() as session:
                for dataset in session.scalars(select(DatasetVersion)):
                    verify_version(dataset)
            final_url = database_url or f'sqlite:///{destination / "database.sqlite"}'
            # Values are quoted for dotenv, and no credentials from the original installation are copied.
            env = 'DATABASE_URL=' + json.dumps(final_url) + '\nARTIFACT_DIR=' + json.dumps(str(destination / 'artifacts')) + '\n'
            (stage / '.env.restored').write_text(env)
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2))
        finally:
            engine.dispose()
        previous = None
        if destination.exists():
            previous = destination.with_name(destination.name + '.previous-' + uuid4().hex)
            destination.rename(previous)
        try:
            # Move entries, not the TemporaryDirectory itself, so cleanup stays valid.
            destination.mkdir()
            for child in list(stage.iterdir()):
                shutil.move(str(child), destination / child.name)
        except Exception:
            if previous and previous.exists():
                if destination.exists():
                    shutil.rmtree(destination)
                previous.rename(destination)
            raise
    return {'destination': str(destination), 'database_url': make_url(final_url).render_as_string(hide_password=True),
            'environment_file': str(destination / '.env.restored'), 'previous_destination': str(previous) if previous else None}
