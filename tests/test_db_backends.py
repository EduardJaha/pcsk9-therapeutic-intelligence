"""Run the same offline integration and migration gates on both database backends."""
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from cvti.api import create_app
from cvti.db import init_db, make_engine


@pytest.fixture(params=['sqlite', 'postgres'])
def backend_url(request, tmp_path):
    if request.param == 'sqlite':
        yield f'sqlite:///{tmp_path / "integration.db"}'
        return
    configured = os.getenv('TEST_DATABASE_URL')
    if not configured:
        pytest.skip('Set TEST_DATABASE_URL to run PostgreSQL integration tests')
    base = create_engine(configured)
    schema = 'cvti_test_' + uuid4().hex
    with base.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(configured).update_query_dict({'options': f'-csearch_path={schema}'})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with base.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        base.dispose()


def test_database_vertical_slice(backend_url, tmp_path):
    with TestClient(create_app(backend_url, str(tmp_path / 'models'))) as client:
        assert client.get('/summary').json()['measurements'] == 0
        assert client.post('/fixtures/load').json()['inserted_measurements'] == 24
        response = client.post('/experiments', json={'source': 'synthetic_fixture'})
        assert response.status_code == 200, response.text
        run = response.json()
        result = client.post('/predict', json={'smiles': 'CC1CCCCC1', 'experiment_id': run['id']})
        assert result.status_code == 200, result.text
        report = client.get(f'/experiments/{run["id"]}/report')
        assert report.status_code == 200
        assert report.json()['dataset_version']['id'] == run['dataset_version_id']
        assert client.get('/summary').json()['predictions'] == 1


def test_supported_migrations_preserve_rows(backend_url):
    config = Config(str(Path(__file__).parents[1] / 'alembic.ini'))
    config.attributes['database_url'] = backend_url
    command.upgrade(config, '2cf3a3fb0c41')
    engine = make_engine(backend_url)
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO target_evidence
            (target_id,target_symbol,disease_id,disease_name,association_score,source_url,retrieved_at)
            VALUES ('PCSK9','PCSK9','TEST','preserved',0.5,'https://example.test',CURRENT_TIMESTAMP)"""))
        conn.execute(text("""INSERT INTO experiments
            (created_at,target_id,data_source,model_kind,activity_type,threshold_pchembl,
             n_molecules,n_scaffolds,metrics,dataset_hash,artifact_path)
            VALUES (CURRENT_TIMESTAMP,'CHEMBL2929','synthetic_fixture','legacy','IC50',6,24,12,'{}','legacy','missing.joblib')"""))
    init_db(engine)
    init_db(engine)  # upgrades are idempotent
    with engine.connect() as conn:
        assert conn.execute(text('SELECT disease_name FROM target_evidence')).scalar_one() == 'preserved'
        assert conn.execute(text('SELECT dataset_version_id FROM experiments')).scalar_one() > 0
        assert conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == ScriptDirectory.from_config(config).get_current_head()
    engine.dispose()
