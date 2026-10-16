from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from cvti.api import create_app
from cvti.db import make_engine, session_factory
from cvti.provenance import create_version


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
        for page in ["Compare molecules", "Molecule profile", "Assay review", "Models & reports", "Datasets & evidence", "Projects & history", "Batch processing"]:
            app.radio[0].set_value(page).run(timeout=20)
            assert not app.exception and not app.error, page
            if page == "Compare molecules":
                next(button for button in app.button if button.label == "Compare molecules").click().run(timeout=20)
                assert not app.exception and not app.error
                assert app.session_state["comparison_result"]["experiment_id"] == run["id"]
                app.text_area[0].set_value("Oc1ccccc1\ninvalid smiles")
                next(button for button in app.button if button.label == "Compare molecules").click().run(timeout=20)
                assert not app.exception and len(app.error) == 1
                assert "comparison_result" not in app.session_state
            elif page == "Molecule profile":
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
        for page in ['Molecule profile', 'Compare molecules', 'Assay review', 'Models & reports',
                     'Datasets & evidence', 'Projects & history', 'Batch processing']:
            app.radio[0].set_value(page).run(timeout=20)
            assert not app.exception and not app.error, page
        job = api.post('/batch-jobs', json={'csv_content': 'smiles\nOc1ccccc1\ninvalid', 'smiles_column': 'smiles'}).json()
        process_next(session_factory(make_engine(url)))
        app.radio[0].set_value('Batch processing').run(timeout=20)
        assert not app.exception and not app.error
        assert api.get(f'/batch-jobs/{job["id"]}').json()['status'] == 'completed'
        assert api.get('/summary').json()['measurements'] == 0
