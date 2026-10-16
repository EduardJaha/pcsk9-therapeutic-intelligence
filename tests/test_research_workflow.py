import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from cvti.api import create_app
from cvti.batches import process_next, recover_jobs
from cvti.db import make_engine, session_factory
from cvti.evaluation import evaluate_existing, prepare_protocol
from cvti.models import BatchJob, DatasetVersion, EvaluationProtocol, Experiment, Prediction
from cvti.provenance import create_version


def test_projects_collections_history_batch_and_report(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "research.db"}'
    factory = session_factory(make_engine(url))
    with TestClient(create_app(url, str(tmp_path / 'models'))) as client:
        assert client.get('/projects').json()[0]['id'] == 1
        project = client.post('/projects', json={'name': 'Research session', 'notes': 'Test'}).json()
        collection = client.post('/collections', json={'project_id': project['id'], 'name': 'Candidates'}).json()
        assert client.post(f'/collections/{collection["id"]}/molecules', json={'smiles': 'Oc1ccccc1', 'notes': 'Example'}).status_code == 200
        assert client.post(f'/collections/{collection["id"]}/molecules', json={'smiles': 'c1ccccc1O'}).status_code == 409
        client.post('/fixtures/load')
        run = client.post('/experiments', json={'project_id': project['id']}).json()
        csv_text = 'name,structure\nfirst,Oc1ccccc1\nduplicate,c1ccccc1O\ninvalid,garbage\nsecond,Cc1ccccc1\n'
        result = client.post('/batch-jobs', json={'project_id': project['id'], 'csv_content': csv_text,
            'smiles_column': 'structure', 'experiment_id': run['id'], 'save_predictions': True})
        assert result.status_code == 200, result.text
        identifier = result.json()['id']
        assert client.get(f'/predictions?project_id={project["id"]}').json()['total'] == 0
        assert process_next(factory) == identifier
        job = client.get(f'/batch-jobs/{identifier}').json()
        assert job['status'] == 'completed'
        assert [r['status'] for r in job['results']] == ['ok', 'duplicate', 'error', 'ok']
        assert client.get('/predictions?project_id=1').json()['total'] == 0
        history = client.get(f'/predictions?project_id={project["id"]}&limit=1').json()
        assert history['total'] == 2 and len(history['items']) == 1
        p = history['items'][0]
        assert p['dataset_version_id'] == run['dataset_version_id']
        exported = client.get(f'/research-reports/{run["id"]}?project_id={project["id"]}&prediction_ids={p["id"]}')
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as bundle:
            manifest = json.loads(bundle.read('manifest.json'))
            assert manifest['prediction_ids'] == [p['id']]
            assert 'dataset-audit.json' in bundle.namelist()
        assert client.get(f'/research-reports/{run["id"]}?project_id=1&prediction_ids={p["id"]}').status_code == 422
        assert client.get(f'/batch-jobs/{identifier}?format=csv').status_code == 200
        assert client.post('/batch-jobs', json={'csv_content': 'wrong\na', 'smiles_column': 'smiles'}).status_code == 422
        assert client.post('/batch-jobs', json={'csv_content': 'smiles\nOc1ccccc1', 'smiles_column': 'smiles', 'save_predictions': True}).status_code == 422
        monkeypatch.setattr('cvti.batches.get_settings', lambda: type('Limits', (), {'batch_max_rows': 1})())
        assert client.post('/batch-jobs', json={'csv_content': csv_text, 'smiles_column': 'structure'}).status_code == 422


def test_worker_checkpoint_and_explicit_retry(tmp_path, monkeypatch):
    import cvti.batches as batches
    url = f'sqlite:///{tmp_path / "resume.db"}'
    factory = session_factory(make_engine(url))
    with TestClient(create_app(url, str(tmp_path / 'models'))) as client:
        client.post('/fixtures/load')
        run = client.post('/experiments', json={}).json()
        job = client.post('/batch-jobs', json={'csv_content': 'smiles\nOc1ccccc1\nCc1ccccc1\n', 'smiles_column': 'smiles',
                                              'experiment_id': run['id'], 'save_predictions': True}).json()
        original = batches.molecule_profile
        calls = 0
        def interrupted(smiles):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('simulated worker failure')
            return original(smiles)
        monkeypatch.setattr(batches, 'molecule_profile', interrupted)
        with pytest.raises(RuntimeError):
            process_next(factory)
        detail = client.get(f'/batch-jobs/{job["id"]}').json()
        assert detail['status'] == 'interrupted' and detail['processed'] == 1
        assert client.get('/predictions').json()['total'] == 1
        monkeypatch.setattr(batches, 'molecule_profile', original)
        assert client.post(f'/batch-jobs/{job["id"]}/retry').status_code == 200
        process_next(factory)
        assert client.get('/predictions').json()['total'] == 2
        with factory() as session:
            row = session.get(BatchJob, job['id'])
            row.status = 'running'
            session.commit()
        recover_jobs(factory)
        assert client.get(f'/batch-jobs/{job["id"]}').json()['status'] == 'interrupted'


def test_fixed_protocol_baselines_external_gate_and_neighbors(tmp_path):
    url = f'sqlite:///{tmp_path / "evaluation.db"}'
    engine = make_engine(url)
    factory = session_factory(engine)
    with TestClient(create_app(url, str(tmp_path / 'models'))) as client:
        client.post('/fixtures/load')
        first = client.post('/experiments', json={}).json()
        with factory() as session:
            version = session.get(DatasetVersion, first['dataset_version_id'])
            protocol, *_ = prepare_protocol(session, version)
            session.commit()
            protocol_id = protocol.id
        models = [client.post('/experiments', json={'dataset_version_id': first['dataset_version_id'],
                  'protocol_id': protocol_id, 'model_kind': name}).json() for name in ['dummy', 'logistic_regression']]
        for result in models:
            assert result['metrics']['evaluation']['protocol_sha256'] == first['metrics']['evaluation']['protocol_sha256']
            assert result['metrics']['evaluation']['splits'][0]['test_smiles'] == first['metrics']['evaluation']['splits'][0]['test_smiles']
        score = client.post('/predict', json={'smiles': 'Oc1ccccc1', 'experiment_id': first['id'], 'save': False}).json()
        assert score['nearest_training_compounds'][0]['tanimoto_similarity'] <= 1
        card = client.get(f'/experiments/{first["id"]}/model-card').json()
        assert card['status'] == 'synthetic_demonstration'
        with factory() as session:
            with pytest.raises(ValueError, match='separate'):
                evaluate_existing(session, first['id'], first['dataset_version_id'])
            records = [{'activity_id': str(i), 'assay_id': 'SYNTHETIC_TEST', 'canonical_smiles': s,
                        'scaffold': 'c1ccccc1', 'pchembl_value': p} for i, (s, p) in enumerate([
                        ('Clc1ccc(C#N)cc1', 7.0), ('Fc1ccc(C(F)(F)F)cc1', 5.0)])]
            external = create_version(session, source='synthetic_fixture', status='ready', target_id=version.target_id,
                                      endpoint_group=None, snapshot_blob=b'{}', review_blob=None, policy={'test': True},
                                      records=records, stats={'synthetic': True})
            session.commit()
            result = evaluate_existing(session, first['id'], external.id)
            assert result['n_molecules'] == 2 and not result['independence_established']
            with pytest.raises(ValueError, match='publication dates'):
                evaluate_existing(session, first['id'], external.id, mode='later')
    engine.dispose()
