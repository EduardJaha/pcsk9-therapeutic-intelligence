import base64
import csv
import io
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from cvti.api import create_app
from cvti.config import Settings
from cvti.curation import curate_snapshot, fetch_snapshot, import_bulk_extract, write_review_sheet
from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import SourceUnavailable, fetch_evidence_snapshot
from cvti.models import DatasetVersion


def activity():
    return {'activity_id': 1, 'assay_chembl_id': 'CHEMBL_TEST', 'molecule_chembl_id': 'CHEMBL_M',
            'target_chembl_id': 'CHEMBL2929', 'target_organism': 'Homo sapiens', 'standard_type': 'IC50',
            'standard_relation': '=', 'standard_units': 'nM', 'standard_value': '100', 'pchembl_value': '7',
            'standard_flag': 1, 'potential_duplicate': 0, 'canonical_smiles': 'Oc1ccccc1',
            'document_chembl_id': 'CHEMBL_DOC'}


def assay():
    return {'assay_chembl_id': 'CHEMBL_TEST', 'target_chembl_id': 'CHEMBL2929', 'relationship_type': 'D',
            'confidence_score': 9, 'assay_type': 'B', 'description': 'Synthetic direct binding test metadata'}


def test_snapshot_completion_and_interruption(tmp_path):
    def capped(request):
        if 'status.json' in str(request.url):
            return httpx.Response(200, json={'chembl_db_version': 'Test release'})
        if 'activity.json' in str(request.url):
            return httpx.Response(200, json={'activities': [activity()], 'page_meta': {'next': '/next', 'total_count': 100}})
        return httpx.Response(200, json={'assays': [assay()], 'page_meta': {'next': None}})
    output = tmp_path / 'capped.json'
    with httpx.Client(transport=httpx.MockTransport(capped)) as client:
        result = fetch_snapshot(output, Settings(chembl_max_records=1), client)
    payload = json.loads(output.read_text())
    assert result['completeness'] == 'incomplete'
    assert payload['pagination']['activities']['status'] == 'capped'
    assert payload['source_release']['release_pinned'] is False
    assert json.loads(base64.b64decode(payload['responses'][1]['body_base64']))['activities'][0]['activity_id'] == 1
    engine = make_engine(f'sqlite:///{tmp_path / "data.db"}')
    init_db(engine)
    with session_factory(engine)() as session:
        with pytest.raises(ValueError, match='incomplete'):
            curate_snapshot(session, output, tmp_path / 'missing.csv')
    engine.dispose()
    def interrupted(request):
        if 'status.json' in str(request.url):
            return httpx.Response(200, json={})
        if 'activity.json' in str(request.url):
            return httpx.Response(200, json={'activities': [activity()], 'page_meta': {'next': None}})
        return httpx.Response(503)
    partial = tmp_path / 'partial.json'
    with httpx.Client(transport=httpx.MockTransport(interrupted)) as client:
        with pytest.raises(SourceUnavailable, match='retained'):
            fetch_snapshot(partial, Settings(http_max_retries=0), client)
    saved = json.loads(partial.read_text())
    assert saved['interrupted'] and len(saved['activities']) == 1
    assert saved['pagination']['assays']['status'] == 'interrupted'


def test_named_extract_review_attribution_and_historical_audit(tmp_path):
    original = tmp_path / 'extract.json'
    original.write_text(json.dumps({'activities': [activity()], 'assays': [assay()]}))
    snapshot = tmp_path / 'snapshot.json'
    import_bulk_extract(original, snapshot, 'ChEMBL test named release')
    assert base64.b64decode(json.loads(snapshot.read_text())['original_extract_base64']) == original.read_bytes()
    sheet = tmp_path / 'review.csv'
    write_review_sheet(snapshot, sheet)
    rows = list(csv.DictReader(io.StringIO(sheet.read_text())))
    rows[0].update(decision='exclude', review_note='Unverified synthetic source')
    def save():
        buffer = io.StringIO(newline='')
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        sheet.write_text(buffer.getvalue())
    save()
    url = f'sqlite:///{tmp_path / "history.db"}'
    engine = make_engine(url)
    init_db(engine)
    with session_factory(engine)() as session:
        first = curate_snapshot(session, snapshot, sheet)
    with TestClient(create_app(url, str(tmp_path / 'models'))) as client:
        before = client.get(f'/dataset-versions/{first["dataset_version_id"]}/audit').json()
        assert not before['software_trainable'] and before['counts']['retained_measurements'] == 0
        rows[0].update(decision='include', endpoint_group='pcsk9_ldlr_binding', review_note='Synthetic protocol checked')
        save()
        rejected = client.post(f'/dataset-versions/{first["dataset_version_id"]}/reviews', json={'csv_content': sheet.read_text()})
        assert rejected.status_code == 422 and 'reviewer' in rejected.text
        rows[0].update(reviewer='Test reviewer', reviewed_at='2026-01-01', primary_source='https://example.test/protocol',
                       species='Homo sapiens', protein_constructs='Test constructs', measurement_method='Test method',
                       experimental_conditions='Synthetic fixture only')
        save()
        accepted = client.post(f'/dataset-versions/{first["dataset_version_id"]}/reviews', json={'csv_content': sheet.read_text()})
        assert accepted.status_code == 200, accepted.text
        second = accepted.json()['dataset_version_id']
        assert second != first['dataset_version_id']
        old = client.get(f'/dataset-versions/{first["dataset_version_id"]}/assays').json()
        assert old['assays'][0]['decision'] == 'exclude'
        current = client.get(f'/dataset-versions/{second}/assays').json()['assays'][0]
        assert current['reviewer'] == 'Test reviewer' and current['primary_source']
        with session_factory(engine)() as session:
            row = session.get(DatasetVersion, second).records_json[0]
            assert row['standard_value'] == '100' and row['standard_units'] == 'nM'
    engine.dispose()


def test_open_targets_context_is_separate_snapshot(tmp_path):
    path = tmp_path / 'evidence.json'
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'data': {'target': {
        'id': 'ENSG00000169174', 'approvedSymbol': 'PCSK9', 'associatedDiseases': {'rows': []}}}}))) as client:
        result = fetch_evidence_snapshot(path, Settings(), client)
    assert result['completeness'] == 'bounded_sample'
    assert json.loads(path.read_text())['purpose'] == 'context_only_not_training_labels'
