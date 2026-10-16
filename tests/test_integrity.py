from pathlib import Path

import joblib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from cvti.api import create_app
from cvti.db import make_engine, session_factory
from cvti.models import Experiment
from cvti.ml import train
from cvti.ingest import ingest_fixture
from cvti.db import init_db


def test_artifact_tamper_is_rejected_before_deserialization(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "integrity.db"}'
    with TestClient(create_app(url, str(tmp_path / 'models'))) as client:
        client.post('/fixtures/load')
        result = client.post('/experiments', json={'source': 'synthetic_fixture'}).json()
        report = client.get(f'/experiments/{result["id"]}/report').json()
        provenance = report['experiment']['training_provenance']
        assert provenance['dependencies']['rdkit']
        assert provenance['fingerprint']['bits'] == 2048
        assert report['experiment']['artifact_sha256']
        assert all(set(s['train_smiles']).isdisjoint(s['test_smiles']) for s in result['metrics']['evaluation']['splits'])
        engine = make_engine(url)
        with session_factory(engine)() as session:
            path = Path(session.get(Experiment, result['id']).artifact_path)
        path.write_bytes(b'changed model')
        monkeypatch.setattr(joblib, 'load', lambda *a: pytest.fail('Must check file hash BEFORE loading pickle'))
        response = client.post('/predict', json={'smiles': 'CC1CCCCC1'})
        assert response.status_code == 422 and 'checksum failed' in response.text
        engine.dispose()


def test_failed_artifact_write_leaves_no_experiment(tmp_path, monkeypatch):
    engine = make_engine(f'sqlite:///{tmp_path / "failure.db"}')
    init_db(engine)
    directory = tmp_path / 'models'
    def broken(bundle, path):
        Path(path).write_bytes(b'partial')
        raise OSError('Disk full')
    with session_factory(engine)() as session:
        ingest_fixture(session)
        monkeypatch.setattr(joblib, 'dump', broken)
        with pytest.raises(OSError, match='Disk full'):
            train(session, artifact_dir=str(directory))
        assert session.scalar(select(Experiment)) is None
        assert list(directory.iterdir()) == []
    engine.dispose()
