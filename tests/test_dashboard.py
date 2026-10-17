from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from cvti.api import create_app
from cvti.db import make_engine, session_factory
from cvti.provenance import create_version


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
        for page in ["Research assistant", "Compare molecules", "Molecule profile", "Assay review", "Models & reports", "Datasets & evidence", "Projects & history", "Batch processing"]:
            app.radio[0].set_value(page).run(timeout=20)
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
        for page in ['Research assistant', 'Molecule profile', 'Compare molecules', 'Assay review', 'Models & reports',
                     'Datasets & evidence', 'Projects & history', 'Batch processing']:
            app.radio[0].set_value(page).run(timeout=20)
            assert not app.exception and not app.error, page
            if page == 'Molecule profile':
                assert next(field for field in app.text_input if field.label == 'SMILES').value == ''
                assert 'molecule_profile' not in app.session_state
            if page == 'Compare molecules':
                assert app.text_area[0].value == ''
                assert 'comparison_result' not in app.session_state
        job = api.post('/batch-jobs', json={'csv_content': 'smiles\nOc1ccccc1\ninvalid', 'smiles_column': 'smiles'}).json()
        process_next(session_factory(make_engine(url)))
        app.radio[0].set_value('Batch processing').run(timeout=20)
        assert not app.exception and not app.error
        assert api.get(f'/batch-jobs/{job["id"]}').json()['status'] == 'completed'
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
        app.radio[0].set_value('Molecule profile').run(timeout=20)
        app.text_input[0].set_value('Oc1ccccc1')
        click(app, 'Build molecule profile')
        click(app, 'Save prediction')
        profile = app.session_state['molecule_profile']
        prediction = app.session_state['profile_prediction']
        app = refresh(app)
        assert app.radio[0].value == 'Molecule profile'
        assert app.text_input[0].value == 'Oc1ccccc1'
        assert app.session_state['molecule_profile'] == profile
        assert app.session_state['profile_prediction'] == prediction
        assert app.session_state['scoring_model'] == run['id']
        assert api.get('/summary').json()['predictions'] == 1

        # Structures-only is an explicit selection, even when models exist.
        next(box for box in app.selectbox if box.label == 'Scoring model').set_value(None).run(timeout=20)
        app.radio[0].set_value('Compare molecules').run(timeout=20)
        app.text_area[0].set_value('Oc1ccccc1\nCc1ccccc1')
        click(app, 'Compare molecules')
        comparison = app.session_state['comparison_result']
        app = refresh(app)
        assert app.text_area[0].value == 'Oc1ccccc1\nCc1ccccc1'
        assert app.session_state['comparison_result'] == comparison
        assert app.session_state['scoring_model'] is None
        app.radio[0].set_value('Molecule profile').run(timeout=20)
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
        app.radio[0].set_value('Compare molecules').run(timeout=20)
        app.text_area[0].set_value('invalid smiles')
        click(app, 'Compare molecules')
        app = refresh(app)
        assert 'comparison_result' not in app.session_state

        # A URL with no workspace identifier never inherits another tab's data.
        fresh = AppTest.from_file(dashboard).run(timeout=20)
        fresh.radio[0].set_value('Molecule profile').run(timeout=20)
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
