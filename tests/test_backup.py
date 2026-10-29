import json
import os
from pathlib import Path
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from cvti.api import create_app
from cvti.backup import create_backup, inspect_backup, restore_backup
from cvti.config import Settings
from cvti.doctor import diagnose
from cvti.workspace_lock import workspace_lock


def _prepare(url, directory):
    with TestClient(create_app(url, str(directory / 'models'))) as client:
        client.post('/fixtures/load')
        response = client.post('/experiments', json={'source': 'synthetic_fixture'})
        assert response.status_code == 200, response.text
        run = response.json()
        prediction = client.post('/predict', json={'smiles': 'CC1CCCCC1'}).json()
        report = client.get(f'/experiments/{run["id"]}/report').json()
        stage = client.post('/registry/imports/preview', json={'csv_content': 'name,smiles\nBackup candidate,Oc1ccccc1\n',
            'smiles_column': 'smiles', 'name_column': 'name', 'modality': 'small_molecule',
            'source_reference': 'Synthetic recovery test'}).json()
        assert client.post(f'/registry/imports/{stage["id"]}/commit', json={'plan_sha256': stage['plan_sha256']}).status_code == 200
    return run, prediction, report


def test_sqlite_backup_relocation_and_tamper(tmp_path):
    directory = tmp_path / 'original'
    directory.mkdir()
    url = f'sqlite:///{directory / "database.db"}'
    run, prediction, report = _prepare(url, directory)
    (directory / 'snapshot.json').write_text('{"source":"test"}')
    for reserved in ('runtime', 'ollama', 'assistant-training', 'workspaces', 'backups'):
        (directory / reserved).mkdir()
        (directory / reserved / 'runtime-metadata.json').write_text('{"not":"research input"}')
    (directory / 'research').mkdir()
    (directory / 'research' / 'retained.json').write_text('{"source":"retained research input"}')
    archive = tmp_path / 'backup.zip'
    with pytest.raises(ValueError, match='services-stopped'):
        create_backup(url, directory / 'models', archive)
    with workspace_lock(url, directory / 'models'):
        with pytest.raises(RuntimeError, match='in use'):
            create_backup(url, directory / 'models', archive, services_stopped=True)
    create_backup(url, directory / 'models', archive, services_stopped=True)
    manifest = inspect_backup(archive)
    assert 'sources/snapshot.json' in manifest['files']
    assert 'sources/research/retained.json' in manifest['files']
    assert not any('runtime-metadata.json' in name for name in manifest['files'])
    destination = tmp_path / 'recovered'
    restore_backup(archive, destination, services_stopped=True)
    settings = Settings(_env_file=destination / '.env.restored')
    assert diagnose(settings)['ok']
    with TestClient(create_app(settings.database_url, settings.artifact_dir)) as client:
        recovered = client.get(f'/experiments/{run["id"]}/report').json()
        assert recovered['dataset_version'] == report['dataset_version']
        result = client.post('/predict', json={'smiles': 'CC1CCCCC1', 'save': False}).json()
        assert result['probability_exploratory_activity'] == prediction['probability_exploratory_activity']
        assert client.get('/summary').json()['predictions'] == 1
        assert client.get('/registry/compounds').json()['items'][0]['name'] == 'Backup candidate'
        assert client.get('/registry/imports/1').json()['status'] == 'committed'
    with pytest.raises(ValueError, match='Destination exists'):
        restore_backup(archive, destination, services_stopped=True)
    tampered = tmp_path / 'tampered.zip'
    with zipfile.ZipFile(archive) as source, zipfile.ZipFile(tampered, 'w') as target:
        for name in source.namelist():
            target.writestr(name, b'changed' if name.endswith('.joblib') else source.read(name))
    with pytest.raises(ValueError, match='checksum'):
        restore_backup(tampered, tmp_path / 'bad', services_stopped=True)
    assert not (tmp_path / 'bad').exists()


def test_postgres_backup_restore(tmp_path):
    configured = os.getenv('TEST_DATABASE_URL')
    if not configured:
        pytest.skip('PostgreSQL restore test needs TEST_DATABASE_URL and client tools')
    admin = create_engine(configured, isolation_level='AUTOCOMMIT')
    names = ['cvti_backup_' + uuid4().hex for _ in range(2)]
    try:
        with admin.connect() as connection:
            for name in names:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
        urls = [make_url(configured).set(database=name).render_as_string(hide_password=False) for name in names]
        original = tmp_path / 'pg_original'
        original.mkdir()
        run, prediction, report = _prepare(urls[0], original)
        archive = tmp_path / 'postgres.zip'
        create_backup(urls[0], original / 'models', archive, services_stopped=True)
        destination = tmp_path / 'pg_restored'
        restore_backup(archive, destination, database_url=urls[1], services_stopped=True)
        with TestClient(create_app(urls[1], str(destination / 'artifacts'))) as client:
            assert client.get(f'/experiments/{run["id"]}/report').json()['dataset_version'] == report['dataset_version']
            assert client.post('/predict', json={'smiles': 'CC1CCCCC1', 'save': False}).json()['probability_exploratory_activity'] == prediction['probability_exploratory_activity']
            assert client.get('/registry/compounds').json()['items'][0]['name'] == 'Backup candidate'
    finally:
        with admin.connect() as connection:
            for name in names:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def test_sqlite_snapshot_connections_are_closed(tmp_path, monkeypatch):
    import sqlite3
    from cvti import backup
    url = f'sqlite:///{tmp_path / "original.db"}'
    _prepare(url, tmp_path)
    original_connect = sqlite3.connect
    opened = []

    class SnapshotConnection(sqlite3.Connection):
        was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs, factory=SnapshotConnection)
        opened.append(connection)
        return connection

    monkeypatch.setattr(backup.sqlite3, 'connect', tracked_connect)
    create_backup(url, tmp_path / 'models', tmp_path / 'snapshot.zip', services_stopped=True)
    assert len(opened) == 2
    assert all(connection.was_closed for connection in opened)


def test_backup_rejects_changed_artifacts_and_unsafe_member_paths(tmp_path):
    url = f'sqlite:///{tmp_path / "corrupt.db"}'
    _prepare(url, tmp_path)
    from cvti.db import make_engine, session_factory
    from cvti.models import Experiment
    from sqlalchemy import select
    engine = make_engine(url)
    with session_factory(engine)() as session:
        run = session.scalar(select(Experiment))
        Path(run.artifact_path).write_bytes(b'tampered')
    with pytest.raises(ValueError, match='checksum failed'):
        create_backup(url, tmp_path / 'models', tmp_path / 'bad.zip', services_stopped=True)
    engine.dispose()
    for member in ['../escaped.txt', 'C:/escaped.txt', '/escaped.txt', '..\\escaped.txt']:
        archive = tmp_path / (str(abs(hash(member))) + '.zip')
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr('manifest.json', '{}')
            bundle.writestr(member, 'bad')
        with pytest.raises(ValueError, match='member path'):
            inspect_backup(archive)
