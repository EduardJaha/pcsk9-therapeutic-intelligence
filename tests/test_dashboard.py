from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from cvti.api import create_app
from cvti.db import make_engine, session_factory
from cvti.provenance import create_version


def select_page(app, page):
    next(radio for radio in app.sidebar.radio if page in radio.options).set_value(page).run(timeout=20)
    assert [radio.value for radio in app.sidebar.radio if radio.value is not None] == [page]
    assert app.query_params["view"] == page


@pytest.fixture(autouse=True)
def disable_local_assistant(monkeypatch, tmp_path):
    from cvti import assistant
    from cvti.config import Settings
    monkeypatch.setattr(assistant, 'get_settings', lambda: Settings(_env_file=None, assistant_model=''))
    monkeypatch.setenv('WORKSPACE_STATE_DIR', str(tmp_path / 'workspaces'))


def test_workbench_navigation_and_read_only_previews(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'workbench.db'}"
    with TestClient(create_app(url, str(tmp_path / "artifacts"))) as api:
        api.post("/fixtures/load")
        run = api.post("/experiments", json={"source": "synthetic_fixture"}).json()
        with session_factory(make_engine(url))() as session:
            create_version(session, source="chembl_curated", status="reviewed_empty", target_id="CHEMBL2929",
                           endpoint_group="pcsk9_ldlr_binding",
                           snapshot_blob=b'{"activities":[{"assay_chembl_id":"CHEMBL100"}],"assays":[]}',
                           review_blob=b"assay_chembl_id,decision,endpoint_group,review_note\nCHEMBL100,exclude,,Different endpoint\n",
                           policy={}, records=[], stats={})
            session.commit()

        class LocalAPI:
            def __init__(self, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def request(self, method, path, **kwargs):
                return api.request(method, path, **kwargs)

        monkeypatch.setattr(httpx, "Client", LocalAPI)
        monkeypatch.delenv("API_URL", raising=False)
        app = AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py")).run(timeout=20)
        assert not app.exception and not app.error
        for page in ["Compound registry", "Candidate workbench", "Assay records", "Research assistant", "Compare molecules", "Molecule profile", "Assay review", "Models & reports", "Datasets & evidence", "Projects & history", "Batch processing"]:
            select_page(app, page)
            assert not app.exception and not app.error, page
            if page == "Compare molecules":
                assert app.text_area[0].value == ""
                app.text_area[0].set_value("Oc1ccccc1\nCc1ccccc1")
                next(button for button in app.button if button.label == "Compare molecules").click().run(timeout=20)
                assert not app.exception and not app.error
                assert app.session_state["comparison_result"]["experiment_id"] == run["id"]
                app.text_area[0].set_value("Oc1ccccc1\ninvalid smiles")
                next(button for button in app.button if button.label == "Compare molecules").click().run(timeout=20)
                assert not app.exception and len(app.error) == 1
                assert "comparison_result" not in app.session_state
            elif page == "Molecule profile":
                assert next(field for field in app.text_input if field.label == "SMILES").value == ""
                next(field for field in app.text_input if field.label == "SMILES").set_value("CC(=O)Oc1ccccc1C(=O)O")
                next(button for button in app.button if button.label == "Build molecule profile").click().run(timeout=20)
                next(button for button in app.button if button.label == "Preview model score").click().run(timeout=20)
                assert not app.exception and not app.error
                assert app.session_state["profile_prediction"]["prediction_id"] is None
            elif page == "Assay review":
                next(box for box in app.selectbox if box.label == "Filter assay decisions").select("include").run(timeout=20)
                assert not app.exception and not app.error
            elif page == "Models & reports":
                assert len(app.get("download_button")) == 2
                next(button for button in app.button if button.label == "Train baseline on synthetic fixture").click().run(timeout=20)
                assert not app.exception and not app.error
                assert api.get("/summary").json()["experiments"] == 2
        assert api.get("/summary").json()["predictions"] == 0


def test_empty_workspace_and_completed_batch_views(tmp_path, monkeypatch):
    from cvti.batches import process_next
    url = f'sqlite:///{tmp_path / "empty.db"}'
    with TestClient(create_app(url, str(tmp_path / 'models'))) as api:
        class LocalAPI:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def request(self, method, path, **kwargs): return api.request(method, path, **kwargs)
        monkeypatch.setattr(httpx, 'Client', LocalAPI)
        monkeypatch.delenv('API_URL', raising=False)
        app = AppTest.from_file(str(Path(__file__).parents[1] / 'dashboard.py')).run(timeout=20)
        assert not app.exception and not app.error
        for page in ['Compound registry', 'Candidate workbench', 'Assay records', 'Research assistant', 'Molecule profile', 'Compare molecules', 'Assay review', 'Models & reports',
                     'Datasets & evidence', 'Projects & history', 'Batch processing']:
            select_page(app, page)
            assert not app.exception and not app.error, page
            if page == 'Molecule profile':
                assert next(field for field in app.text_input if field.label == 'SMILES').value == ''
                assert 'molecule_profile' not in app.session_state
            if page == 'Compare molecules':
                assert app.text_area[0].value == ''
                assert 'comparison_result' not in app.session_state
        job = api.post('/batch-jobs', json={'csv_content': 'smiles\nOc1ccccc1\ninvalid', 'smiles_column': 'smiles'}).json()
        process_next(session_factory(make_engine(url)))
        select_page(app, 'Batch processing')
        assert not app.exception and not app.error
        assert api.get(f'/batch-jobs/{job["id"]}').json()['status'] == 'completed'
        assert api.get('/summary').json()['measurements'] == 0


def test_collection_search_in_dashboard_does_not_write_research_records(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "collection-search.db"}'
    with TestClient(create_app(url, str(tmp_path / 'models'))) as api:
        collection = api.post('/collections', json={'project_id': 1, 'name': 'Candidates'}).json()
        api.post(f'/collections/{collection["id"]}/molecules', json={'smiles': 'Oc1ccccc1'})

        class LocalAPI:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def request(self, method, path, **kwargs): return api.request(method, path, **kwargs)

        monkeypatch.setattr(httpx, 'Client', LocalAPI)
        monkeypatch.delenv('API_URL', raising=False)
        app = AppTest.from_file(str(Path(__file__).parents[1] / 'dashboard.py')).run(timeout=20)
        select_page(app, 'Projects & history')
        next(field for field in app.text_input if field.label == 'Search SMILES').set_value('c1ccccc1O')
        next(button for button in app.button if button.label == 'Search structures').click().run(timeout=20)
        assert not app.exception and not app.error, [item.value for item in app.error]
        assert app.session_state['collection_search_result']['total_hits'] == 1
        assert api.get('/summary').json()['predictions'] == 0
        next(field for field in app.text_input if field.label == 'Search SMILES').set_value('invalid')
        next(button for button in app.button if button.label == 'Search structures').click().run(timeout=20)
        assert len(app.error) == 1
        assert app.session_state.get('collection_search_result') is None


def test_registry_materials_assay_records_and_candidate_views_in_dashboard(tmp_path, monkeypatch):
    url = f'sqlite:///{tmp_path / "integrated-registry.db"}'
    with TestClient(create_app(url, str(tmp_path / 'models'))) as api:
        class LocalAPI:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def request(self, method, path, **kwargs): return api.request(method, path, **kwargs)

        monkeypatch.setattr(httpx, 'Client', LocalAPI)
        monkeypatch.delenv('API_URL', raising=False)
        app = AppTest.from_file(str(Path(__file__).parents[1] / 'dashboard.py')).run(timeout=20)

        def field(label):
            return next(item for item in app.text_input if item.label == label)

        def choose(label, value):
            next(item for item in app.selectbox if item.label == label).set_value(value)

        def click(label):
            next(item for item in app.button if item.label == label).click().run(timeout=20)
            assert not app.exception and not app.error, [item.value for item in app.error]

        select_page(app, 'Compound registry')
        assert field('Registry SMILES').value == ''
        field('Registry SMILES').set_value('Oc1ccccc1')
        field('Compound name (optional)').set_value('UI test compound')
        field('Structure source reference').set_value('Synthetic test source')
        choose('Compound modality', 'small_molecule')
        click('Register compound')
        field('Batch name').set_value('UI batch')
        field('Batch source reference').set_value('Synthetic test batch')
        choose('Batch data origin', 'synthetic')
        click('Record batch')
        field('Sample name').set_value('UI sample')
        click('Record sample')
        sample = api.get('/registry/materials').json()['samples'][0]
        protocol = api.post('/registry/protocols', json={'name': 'UI protocol', 'endpoint': 'pcsk9_ldlr_binding',
            'activity_type': 'IC50', 'units': 'nM', 'modality': 'small_molecule', 'species': 'Human',
            'constructs': 'Synthetic construct', 'method': 'Synthetic method', 'conditions': 'Synthetic conditions',
            'source_reference': 'Synthetic test protocol'}).json()
        api.post('/registry/runs', json={'protocol_id': protocol['id'], 'name': 'UI run', 'performed_on': '2026-10-10',
            'operator': 'Test operator', 'data_origin': 'synthetic', 'source_reference': 'Synthetic test run'})
        select_page(app, 'Assay records')
        field('Source result identifier').set_value('UI result 1')
        field('Original numeric value').set_value('2.500')
        field('Observation source reference').set_value('Synthetic test row')
        click('Record observation')
        recorded = api.get('/registry/observations').json()['items']
        assert len(recorded) == 1 and recorded[0]['sample_id'] == sample['id'] and recorded[0]['value_text'] == '2.500'
        select_page(app, 'Candidate workbench')
        assert app.session_state['candidate_result']['total_hits'] == 1
        field('New candidate view name').set_value('UI saved view')
        click('Save applied candidate view')
        click('Run saved candidate view')
        assert api.get('/registry/views').json()[0]['name'] == 'UI saved view'
        other = api.post('/projects', json={'name': 'Other project'}).json()
        app.run(timeout=20)
        choose('Research project', other['id'])
        app.run(timeout=20)
        assert app.session_state['candidate_result']['project_id'] == other['id']
        assert app.session_state['candidate_result']['total_hits'] == 0
        assert api.get('/summary').json()['predictions'] == 0
        assert api.get('/summary').json()['measurements'] == 0


def test_browser_refresh_restores_molecules_without_repeating_requests(tmp_path, monkeypatch):
    dashboard = str(Path(__file__).parents[1] / 'dashboard.py')
    with TestClient(create_app(f'sqlite:///{tmp_path / "refresh.db"}', str(tmp_path / 'models'))) as api:
        api.post('/fixtures/load')
        run = api.post('/experiments', json={'source': 'synthetic_fixture'}).json()
        requests = []

        class LocalAPI:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def request(self, method, path, **kwargs):
                requests.append((method, path))
                return api.request(method, path, **kwargs)

        monkeypatch.setattr(httpx, 'Client', LocalAPI)
        monkeypatch.delenv('API_URL', raising=False)

        def refresh(previous):
            # A real refresh retains the URL but loses ALL Streamlit session state.
            fresh = AppTest.from_file(dashboard)
            fresh.query_params.update(previous.query_params)
            requests.clear()
            fresh.run(timeout=20)
            assert not fresh.exception and not fresh.error
            assert all(method == 'GET' for method, _ in requests)
            return fresh

        def click(app, label):
            next(button for button in app.button if button.label == label).click().run(timeout=20)

        app = AppTest.from_file(dashboard).run(timeout=20)
        select_page(app, 'Molecule profile')
        app.text_input[0].set_value('Oc1ccccc1')
        click(app, 'Build molecule profile')
        click(app, 'Save prediction')
        profile = app.session_state['molecule_profile']
        prediction = app.session_state['profile_prediction']
        app = refresh(app)
        assert app.session_state["workspace_nav"] == 'Molecule profile'
        assert app.text_input[0].value == 'Oc1ccccc1'
        assert app.session_state['molecule_profile'] == profile
        assert app.session_state['profile_prediction'] == prediction
        assert app.session_state['scoring_model'] == run['id']
        assert api.get('/summary').json()['predictions'] == 1

        # Structures-only is an explicit selection, even when models exist.
        next(box for box in app.selectbox if box.label == 'Scoring model').set_value(None).run(timeout=20)
        select_page(app, 'Compare molecules')
        app.text_area[0].set_value('Oc1ccccc1\nCc1ccccc1')
        click(app, 'Compare molecules')
        comparison = app.session_state['comparison_result']
        app = refresh(app)
        assert app.text_area[0].value == 'Oc1ccccc1\nCc1ccccc1'
        assert app.session_state['comparison_result'] == comparison
        assert app.session_state['scoring_model'] is None
        select_page(app, 'Molecule profile')
        assert app.text_input[0].value == 'Oc1ccccc1'

        project = api.post('/projects', json={'name': 'Other project'}).json()
        app.run(timeout=20)
        next(box for box in app.selectbox if box.label == 'Research project').set_value(project['id']).run(timeout=20)
        assert app.text_input[0].value == ''
        assert 'molecule_profile' not in app.session_state
        assert 'comparison_result' not in app.session_state
        app.text_input[0].set_value('Cc1ccccc1')
        click(app, 'Build molecule profile')
        app = refresh(app)
        assert app.session_state['active_project'] == project['id']
        assert app.text_input[0].value == 'Cc1ccccc1'
        assert app.session_state['molecule_profile']['canonical_smiles'] == 'Cc1ccccc1'

        # Invalid submissions must remove persisted output too.
        app.text_input[0].set_value('invalid smiles')
        click(app, 'Build molecule profile')
        assert len(app.error) == 1
        app = refresh(app)
        assert 'molecule_profile' not in app.session_state
        assert 'profile_prediction' not in app.session_state
        select_page(app, 'Compare molecules')
        app.text_area[0].set_value('invalid smiles')
        click(app, 'Compare molecules')
        app = refresh(app)
        assert 'comparison_result' not in app.session_state

        # A URL with no workspace identifier never inherits another tab's data.
        fresh = AppTest.from_file(dashboard).run(timeout=20)
        select_page(fresh, 'Molecule profile')
        assert fresh.text_input[0].value == ''
        assert 'molecule_profile' not in fresh.session_state
        assert fresh.query_params['workspace'] != app.query_params['workspace']
        assert api.get('/summary').json()['predictions'] == 1


def test_workspace_storage_failure_keeps_dashboard_usable(tmp_path, monkeypatch):
    blocked = tmp_path / 'not-a-directory'
    blocked.write_text('blocked')
    monkeypatch.setenv('WORKSPACE_STATE_DIR', str(blocked))

    class LocalAPI:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def request(self, method, path, **kwargs):
            request = httpx.Request(method, path)
            payload = {'measurements': 0} if path.endswith('/summary') else []
            return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx, 'Client', LocalAPI)
    app = AppTest.from_file(str(Path(__file__).parents[1] / 'dashboard.py')).run(timeout=20)
    assert not app.exception and not app.error
    assert any('could not be saved locally' in warning.value for warning in app.warning)
