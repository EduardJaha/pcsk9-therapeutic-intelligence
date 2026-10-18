import io
import json
import zipfile

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from cvti.api import create_app
from cvti.db import Base, make_engine, session_factory
from cvti.models import DatasetVersion, Experiment, Measurement, RegisteredCompound, RegistrationImport, ResearchView
from cvti.provenance import digest


@pytest.fixture
def lab(tmp_path):
    url = f'sqlite:///{tmp_path / "registry.db"}'
    engine = make_engine(url)
    try:
        with TestClient(create_app(url, str(tmp_path / 'models'))) as client:
            yield client, session_factory(engine)
    finally:
        engine.dispose()


def post(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def register(client, smiles='Oc1ccccc1', project_id=1, modality='small_molecule', name='Candidate'):
    return post(client, '/registry/compounds', {'smiles': smiles, 'project_id': project_id,
        'modality': modality, 'name': name, 'source_reference': 'Synthetic test notebook 1'})


def material(client, compound_id, project_id=1, origin='synthetic'):
    batch = post(client, '/registry/batches', {'compound_id': compound_id, 'project_id': project_id,
        'name': 'Batch A', 'data_origin': origin, 'source_reference': 'Synthetic test batch record'})
    sample = post(client, '/registry/samples', {'batch_id': batch['id'], 'project_id': project_id,
        'name': 'Vial A', 'location': 'Test location'})
    return batch, sample


def protocol_run(client, project_id=1, origin='synthetic', modality='small_molecule', name='Binding'):
    protocol = post(client, '/registry/protocols', {'project_id': project_id, 'name': name,
        'endpoint': 'pcsk9_ldlr_binding', 'activity_type': 'IC50', 'units': 'nM', 'modality': modality,
        'species': 'Human', 'constructs': 'Synthetic protocol construct', 'method': 'Synthetic FRET method',
        'conditions': 'Synthetic test conditions', 'source_reference': 'Synthetic test protocol'})
    run = post(client, '/registry/runs', {'project_id': project_id, 'protocol_id': protocol['id'],
        'name': 'Run A', 'performed_on': '2026-10-10', 'operator': 'Test operator',
        'data_origin': origin, 'source_reference': 'Synthetic test run'})
    return protocol, run


def test_registry_identity_preserves_original_and_accepts_non_training_structures(lab):
    client, factory = lab
    registered = register(client, '[Na+].[O-]c1ccccc1', name='Original')
    assert registered['created'] and registered['canonical_smiles'] == 'Oc1ccccc1'
    assert registered['input_smiles'] == '[Na+].[O-]c1ccccc1'
    assert registered['warnings'] and registered['policy'] == 'registry-charge-parent-v1'
    duplicate = register(client, 'c1ccccc1O', name='Replacement must not overwrite')
    assert not duplicate['created'] and duplicate['id'] == registered['id'] and duplicate['name'] == 'Original'
    assert client.post('/registry/compounds', json={'smiles': 'c1ccccc1O', 'modality': 'peptide',
                                                  'source_reference': 'Test'}).status_code == 409
    acyclic = register(client, 'CCO')
    assert acyclic['created'] and acyclic['formula'] == 'C2H6O'
    assert client.post('/molecules/profile', json={'smiles': 'CCO'}).status_code == 422
    first = register(client, 'C[C@H](O)c1ccccc1')
    second = register(client, 'C[C@@H](O)c1ccccc1')
    assert first['id'] != second['id']
    assert register(client, 'CC(O)c1ccccc1')['warnings']
    other = post(client, '/projects', {'name': 'Other project'})
    assert register(client, project_id=other['id'])['id'] != registered['id']
    assert client.get(f'/registry/compounds/{registered["id"]}', params={'project_id': other['id']}).status_code == 404
    assert client.post('/registry/compounds', json={'smiles': 'Oc1ccccc1', 'modality': 'small_molecule',
                                                  'source_reference': '  '}).status_code == 422
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Measurement)) == 0
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 0


def test_staged_csv_registration_is_explicit_idempotent_and_checks_exact_input(lab):
    client, factory = lab
    register(client)
    content = '\ufefflabel,structure,comment\r\nold,Oc1ccccc1,kept\r\nnew,CCO,new\r\ndup,OCC,duplicate\r\nbad,invalid,unusable\r\n'
    stage = post(client, '/registry/imports/preview', {'csv_content': content, 'smiles_column': 'structure',
        'name_column': 'label', 'notes_column': 'comment', 'modality': 'small_molecule', 'source_reference': 'Test CSV'})
    assert stage['counts'] == {'existing': 1, 'ready': 1, 'duplicate': 1, 'error': 1}
    assert stage['input_sha256'] == digest(content.encode())
    assert client.get('/registry/compounds').json()['total'] == 1
    path = f'/registry/imports/{stage["id"]}/commit'
    assert client.post(path, json={'plan_sha256': '0' * 64}).status_code == 409
    result = post(client, path, {'plan_sha256': stage['plan_sha256']})
    assert result['outcome']['created'] == 1 and result['outcome']['existing'] == 1
    assert post(client, path, {'plan_sha256': stage['plan_sha256']})['outcome'] == result['outcome']
    assert client.get('/registry/compounds').json()['total'] == 2
    exported = client.get('/registry/export')
    with zipfile.ZipFile(io.BytesIO(exported.content)) as bundle:
        assert bundle.read(f'imports/{stage["id"]}.csv') == content.encode()
        manifest = json.loads(bundle.read('manifest.json'))
        assert all(digest(bundle.read(name)) == checksum for name, checksum in manifest['files_sha256'].items())
    with factory() as session:
        saved = session.get(RegistrationImport, stage['id'])
        saved.csv_content += 'tampered'
        session.commit()
    assert client.post(path, json={'plan_sha256': stage['plan_sha256']}).status_code == 409


def test_csv_preview_and_atomic_commit_reject_ambiguous_changed_and_malformed_input(lab):
    client, factory = lab
    base = {'smiles_column': 'smiles', 'modality': 'small_molecule', 'source_reference': 'Test'}
    for content in ['smiles,smiles\nCCO,CCO', 'wrong\nCCO', 'smiles\n"unterminated', '"unterminated', 'smiles\n']:
        assert client.post('/registry/imports/preview', json={**base, 'csv_content': content}).status_code == 422
    bad_width = post(client, '/registry/imports/preview', {**base, 'csv_content': 'smiles,name\nCCO,extra,unexpected\nCCO\n'})
    assert bad_width['counts'] == {'error': 2}
    stage = post(client, '/registry/imports/preview', {**base, 'csv_content': 'smiles\nCCO\nCc1ccccc1\n'})
    register(client, 'Cc1ccccc1', modality='other')
    assert client.post(f'/registry/imports/{stage["id"]}/commit', json={'plan_sha256': stage['plan_sha256']}).status_code == 409
    assert client.get('/registry/compounds').json()['total'] == 1  # first CSV row was rolled back
    assert client.get(f'/registry/imports/{stage["id"]}').json()['status'] == 'preview'
    with factory() as session:
        record = session.get(RegistrationImport, stage['id'])
        record.rows_json = []
        session.commit()
    assert client.post(f'/registry/imports/{stage["id"]}/commit', json={'plan_sha256': stage['plan_sha256']}).status_code == 409


def test_assay_observations_retain_readout_context_and_enforce_material_compatibility(lab):
    client, factory = lab
    compound = register(client)
    batch, sample = material(client, compound['id'])
    protocol, run = protocol_run(client)
    payload = {'run_id': run['id'], 'sample_id': sample['id'], 'source_record_id': 'replicate-1',
               'value_text': ' 12.3400 ', 'relation': '<', 'units': 'nM', 'source_reference': 'Test table row 1'}
    result = post(client, '/registry/observations', payload)
    assert result['review_status'] == 'recorded_unreviewed' and result['value_text'] == ' 12.3400 '
    assert client.post('/registry/observations', json=payload).status_code == 409
    for patch in [{'units': 'uM'}, {'value_text': 'NaN'}, {'value_text': 'Infinity'}, {'value_text': 'not a number'}]:
        assert client.post('/registry/observations', json={**payload, 'source_record_id': 'invalid', **patch}).status_code == 422
    _, research_run = protocol_run(client, origin='research', name='Research binding')
    assert client.post('/registry/observations', json={**payload, 'run_id': research_run['id']}).status_code == 422
    peptide = register(client, 'NC(=O)c1ccccc1', modality='peptide')
    _, peptide_sample = material(client, peptide['id'])
    assert client.post('/registry/observations', json={**payload, 'sample_id': peptide_sample['id']}).status_code == 422
    other = post(client, '/projects', {'name': 'Other'})
    for path, data in [('/registry/batches', {'compound_id': compound['id'], 'name': 'Invalid', 'data_origin': 'synthetic', 'source_reference': 'Test'}),
                       ('/registry/samples', {'batch_id': batch['id'], 'name': 'Invalid'}),
                       ('/registry/runs', {'protocol_id': protocol['id'], 'name': 'Invalid', 'performed_on': '2026-10-10', 'operator': 'Test', 'data_origin': 'synthetic', 'source_reference': 'Test'}),
                       ('/registry/observations', payload)]:
        assert client.post(path, json={**data, 'project_id': other['id']}).status_code == 404
    row = client.get('/registry/observations').json()['items'][0]
    assert row['endpoint'] == 'pcsk9_ldlr_binding' and row['activity_type'] == 'IC50' and row['units'] == 'nM'
    assert row['batch_id'] == batch['id'] and row['relation'] == '<' and row['data_origin'] == 'synthetic'
    assert row['conditions'] == 'Synthetic test conditions' and row['numeric_value'] == 12.34
    correction = post(client, '/registry/observations', {**payload, 'source_record_id': 'replicate-1-corrected',
        'value_text': '10.2500', 'supersedes_id': row['id'], 'notes': 'Transcription corrected against the test source'})
    revised = client.get('/registry/observations').json()['items']
    assert len(revised) == 2 and revised[0]['value_text'] == ' 12.3400 ' and not revised[0]['is_current']
    assert revised[1]['is_current'] and revised[1]['supersedes_id'] == row['id']
    assert client.post('/registry/observations', json={**payload, 'source_record_id': 'branch',
        'supersedes_id': row['id'], 'notes': 'A conflicting correction'}).status_code == 409
    assert correction['id'] != row['id']
    assert client.get('/registry/observations', params={'project_id': other['id']}).json()['items'] == []
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(Measurement)) == 0
        assert session.scalar(select(func.count()).select_from(DatasetVersion)) == 0
    assert client.post('/experiments', json={'source': 'chembl_curated'}).status_code == 422


def test_candidate_views_filter_and_rerun_with_current_registry_and_scope_exports(lab):
    client, factory = lab
    first = register(client, name='Reference')
    register(client, 'CCO', name='Solvent example')
    search = post(client, '/registry/workbench/search', {'criteria': {'query_smiles': 'Oc1ccccc1',
        'match_mode': 'similarity', 'min_similarity': 0}})
    assert search['items'][0]['id'] == first['id'] and search['items'][0]['similarity'] == 1.0
    criteria = {'min_mw': 80, 'max_mw': 150, 'modality': 'small_molecule', 'query_smiles': 'c1ccccc1', 'match_mode': 'substructure'}
    assert post(client, '/registry/workbench/search', {'criteria': criteria})['total_hits'] == 1
    view = post(client, '/registry/views', {'name': 'Aromatic candidates', 'criteria': criteria})
    register(client, 'Cc1ccccc1', name='New candidate')
    assert post(client, f'/registry/views/{view["id"]}/run', {})['total_hits'] == 2
    assert client.post('/registry/workbench/search', json={'criteria': {'min_mw': 100, 'max_mw': 80}}).status_code == 422
    assert client.post('/registry/workbench/search', json={'criteria': {'query_smiles': 'CCO'}}).status_code == 422
    other = post(client, '/projects', {'name': 'Other'})
    register(client, 'Cc1ccccc1O', project_id=other['id'], name='Other project private record')
    assert client.post(f'/registry/views/{view["id"]}/run', json={'project_id': other['id']}).status_code == 404
    with zipfile.ZipFile(io.BytesIO(client.get('/registry/export').content)) as bundle:
        assert b'Other project private record' not in bundle.read('compounds.json')
    with factory() as session:
        record = session.get(ResearchView, view['id'])
        record.criteria_json = {'name': 'tampered'}
        session.commit()
    assert client.post(f'/registry/views/{view["id"]}/run', json={}).status_code == 409


def test_candidate_scoring_is_explicit_attributed_read_only_and_reports_failures(lab):
    client, factory = lab
    ring = register(client)
    acyclic = register(client, 'CCO')
    peptide = register(client, 'NC(=O)c1ccccc1', modality='peptide')
    post(client, '/fixtures/load', {})
    run = post(client, '/experiments', {})
    payload = {'experiment_id': run['id'], 'compound_ids': [ring['id'], acyclic['id'], peptide['id']]}
    result = post(client, '/registry/workbench/score', payload)
    assert [row['status'] for row in result['items']] == ['ok', 'error', 'error']
    assert result['model_card']['status'] == 'synthetic_demonstration' and not result['predictions_saved']
    prediction = result['items'][0]['prediction']
    assert prediction['prediction_id'] is None and prediction['artifact_integrity'] == 'verified'
    assert prediction['dataset_version_id'] == run['dataset_version_id']
    assert client.get('/summary').json()['predictions'] == 0
    other = post(client, '/projects', {'name': 'Other'})
    assert client.post('/registry/workbench/score', json={**payload, 'project_id': other['id']}).status_code == 404
    foreign = register(client, 'Cc1ccccc1', project_id=other['id'])
    assert client.post('/registry/workbench/score', json={**payload, 'compound_ids': [foreign['id']]}).status_code == 404
    assert client.post('/registry/workbench/score', json={'compound_ids': [ring['id']]}).status_code == 422
    with factory() as session:
        experiment = session.get(Experiment, run['id'])
        experiment.artifact_path = 'missing-model.joblib'
        session.commit()
    assert post(client, '/registry/workbench/score', payload)['items'][0]['status'] == 'error'


def test_registry_migration_matches_metadata(lab):
    _, factory = lab
    with factory().bind.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection, opts={'compare_type': True}), Base.metadata) == []


def test_registry_export_snapshot_does_not_mix_concurrent_changes(lab):
    from cvti.registry import register_compound
    from cvti.registry_api import database
    from cvti.registry_schemas import CompoundInput
    client, factory = lab
    register(client)
    engine = factory.kw['bind']
    with engine.connect() as connection:
        connection.exec_driver_sql('PRAGMA journal_mode=WAL')
    with database(factory, snapshot=True) as snapshot:
        count = select(func.count()).select_from(RegisteredCompound)
        assert snapshot.scalar(count) == 1
        with factory() as writer:
            register_compound(writer, CompoundInput(smiles='CCO', modality='small_molecule', source_reference='Synthetic concurrent test'))
            writer.commit()
        assert snapshot.scalar(count) == 1
    assert client.get('/registry/compounds').json()['total'] == 2
