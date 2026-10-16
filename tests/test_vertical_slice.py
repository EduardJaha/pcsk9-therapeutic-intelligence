import httpx
import numpy as np
import pytest
from types import SimpleNamespace
from pathlib import Path
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select, text

from cvti.api import create_app
from cvti.chemistry import standardize
from cvti.config import Settings
from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import SourceUnavailable, ingest_live, request_json
from cvti.models import DatasetVersion, Experiment, Measurement, TargetEvidence
from cvti.ml import _evaluation_splits, _examples
from cvti.provenance import verify_version
from cvti.reports import experiment_report


def test_offline_api_vertical_slice(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", str(tmp_path / "artifacts"))
    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        first = client.post("/fixtures/load").json()
        assert first["inserted_measurements"] == 24
        assert client.post("/fixtures/load").json()["inserted_measurements"] == 0
        run = client.post("/experiments", json={"source": "synthetic_fixture"})
        assert run.status_code == 200, run.text
        data = run.json()
        assert data["n_molecules"] == 24
        assert data["dataset_version_id"] > 0
        version = client.get(f"/dataset-versions/{data['dataset_version_id']}")
        assert version.status_code == 200
        assert version.json()["source"] == "synthetic_fixture"
        assert version.json()["records"] == 24
        metrics = data["metrics"]
        assert sum(metrics["class_counts"].values()) == 24
        assert metrics["class_counts"]["active"] > 0
        assert metrics["class_counts"]["inactive"] > 0
        evaluation = metrics["evaluation"]
        assert len(evaluation["splits"]) == 5
        assert evaluation["split_selection"]["attempted"] >= 5
        assert len({split["test_scaffold_sha256"] for split in evaluation["splits"]}) == 5
        for split in evaluation["splits"]:
            assert split["scaffold_overlap"] == split["molecule_overlap"] == 0
            assert split["n_test_scaffolds"] > 0
            assert sum(split["train_class_counts"].values()) + sum(split["test_class_counts"].values()) == 24
            assert all(count > 0 for count in split["train_class_counts"].values())
            assert all(count > 0 for count in split["test_class_counts"].values())
            assert sum(split["confusion_matrix"].values()) == sum(split["test_class_counts"].values())
            assert 0 <= split["balanced_accuracy"] <= 1
            assert 0 <= split["roc_auc"] <= 1
            assert 0 <= split["average_precision"] <= 1
        for metric in ("balanced_accuracy", "roc_auc", "average_precision"):
            scores = [split[metric] for split in evaluation["splits"]]
            assert evaluation["summary"][metric]["min"] == min(scores)
            assert evaluation["summary"][metric]["max"] == max(scores)
        report = client.get(f"/experiments/{data['id']}/report").json()
        assert report["experiment"]["metrics"] == metrics
        assert report["dataset_version"]["id"] == data["dataset_version_id"]
        assert report["assay_reviews"] == []
        markdown = client.get(f"/experiments/{data['id']}/report?format=markdown")
        assert markdown.status_code == 200
        assert "Dataset classes:" in markdown.text
        assert "| 5 |" in markdown.text
        assert "synthetic_fixture" in markdown.text
        profile = client.post("/molecules/profile", json={"smiles": "Oc1ccccc1"})
        assert profile.status_code == 200
        assert profile.json()["formula"] == "C6H6O"
        assert profile.json()["properties"]["molecular_weight"] == pytest.approx(94.11, abs=0.02)
        assert "<svg" in profile.json()["svg"]
        assert client.post("/molecules/profile", json={"smiles": "invalid smiles"}).status_code == 422
        comparison = client.post("/molecules/compare", json={"smiles": ["Oc1ccccc1", "Cc1ccccc1"],
                                                               "experiment_id": data["id"]})
        assert comparison.status_code == 200, comparison.text
        assert comparison.json()["predictions_saved"] is False
        assert len(comparison.json()["chemical_space"]["points"]) == 2
        assert all(np.isfinite(point["pc1"]) and np.isfinite(point["pc2"])
                   for point in comparison.json()["chemical_space"]["points"])
        for molecule in comparison.json()["molecules"]:
            assert molecule["prediction"]["experiment_id"] == data["id"]
            assert molecule["prediction"]["prediction_id"] is None
        structures_only = client.post("/molecules/compare", json={"smiles": ["Oc1ccccc1", "Cc1ccccc1"]})
        assert structures_only.status_code == 200
        assert all(m["prediction"] is None for m in structures_only.json()["molecules"])
        for values in (["Oc1ccccc1", "c1ccccc1O"], ["Oc1ccccc1", "invalid"], ["Oc1ccccc1"] * 7):
            assert client.post("/molecules/compare", json={"smiles": values}).status_code == 422
        assert client.post("/molecules/compare", json={"smiles": ["Oc1ccccc1", "Cc1ccccc1"],
                                                       "experiment_id": 999}).status_code == 422
        assert client.get("/summary").json()["predictions"] == 0
        preview = client.post("/predict", json={"smiles": "CC1CCCCC1", "experiment_id": data["id"], "save": False})
        assert preview.status_code == 200
        assert preview.json()["prediction_id"] is None
        assert client.get("/summary").json()["predictions"] == 0
        prediction = client.post("/predict", json={"smiles": "CC1CCCCC1"})
        assert prediction.status_code == 200, prediction.text
        assert 0 <= prediction.json()["probability_exploratory_activity"] <= 1
        assert prediction.json()["label"].startswith("Research hypothesis")
        assert prediction.json()["dataset_version_id"] == data["dataset_version_id"]
        assert client.get("/summary").json()["predictions"] == 1
        assert client.get("/evidence").json()[0]["disease_id"].startswith("SYNTHETIC")


def test_standardization_and_invalid_molecule():
    assert standardize("[Na+].O=C([O-])c1ccccc1")[0] == "O=C(O)c1ccccc1"
    with pytest.raises(ValueError):
        standardize("not a smiles")


def test_structure_comparison_handles_identical_fingerprints_without_nan(tmp_path):
    with TestClient(create_app(f"sqlite:///{tmp_path / 'structures.db'}")) as client:
        result = client.post("/molecules/compare", json={"smiles": ["C[C@H]1CCCCO1", "C[C@@H]1CCCCO1"]})
        assert result.status_code == 200, result.text
        assert result.json()["chemical_space"]["explained_variance_ratio"] == [0.0, 0.0]
        assert all(point["pc1"] == 0 and point["pc2"] == 0 for point in result.json()["chemical_space"]["points"])
        assert client.get("/summary").json()["predictions"] == 0


def test_retry_after_rate_limit(monkeypatch):
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr("cvti.ingest.random.uniform", lambda *_: 0)
    settings = Settings(http_max_retries=1, http_backoff_seconds=0)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert request_json(client, "GET", "https://example.test", settings) == {"ok": True}
    assert calls == 2


def test_live_ingest_filters_and_persists(tmp_path):
    activity = {
        "activity_id": 901, "target_chembl_id": "CHEMBL2929", "standard_type": "IC50",
        "standard_relation": "=", "standard_units": "nM", "pchembl_value": "7.0",
        "canonical_smiles": "Oc1ccccc1", "potential_duplicate": 0,
        "molecule_chembl_id": "CHEMBL_TEST", "assay_chembl_id": "CHEMBL_ASSAY",
    }

    def handler(request):
        if "activity.json" in str(request.url):
            return httpx.Response(200, json={"activities": [activity, {**activity, "activity_id": 902, "standard_relation": ">"}],
                                              "page_meta": {"next": None}})
        return httpx.Response(200, json={"data": {"target": {
            "id": "ENSG00000169174", "approvedSymbol": "PCSK9",
            "associatedDiseases": {"rows": [{"score": 0.7, "disease": {"id": "EFO_TEST", "name": "Test disease"}}]}
        }}})

    engine = make_engine(f"sqlite:///{tmp_path / 'live.db'}")
    init_db(engine)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client, session_factory(engine)() as session:
        result = ingest_live(session, Settings(chembl_max_records=2), client)
        assert result["inserted_measurements"] == 1
        row = session.scalar(select(Measurement))
        assert row.source == "chembl" and row.pchembl_value == 7


def test_exhausted_rate_limit_is_clear():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(429))) as client:
        with pytest.raises(SourceUnavailable, match="HTTP 429 after retries"):
            request_json(client, "GET", "https://example.test", Settings(http_max_retries=0))


def test_conflicting_duplicate_molecule_is_excluded():
    rows = [SimpleNamespace(canonical_smiles="Oc1ccccc1", scaffold="c1ccccc1", pchembl_value=value)
            for value in (5.5, 6.5)]
    examples, conflicts = _examples(rows)
    assert examples == []
    assert conflicts == 1


def test_repeated_evaluation_stops_when_class_valid_scaffold_splits_are_impossible():
    groups = np.array(["a", "a", "b", "b", "c", "c", "d", "d", "e", "e"])
    labels = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    with pytest.raises(ValueError, match="five|5 distinct scaffold splits"):
        _evaluation_splits(np.zeros((10, 2)), labels, groups)


def test_migration_preserves_legacy_database(tmp_path):
    url = f"sqlite:///{tmp_path / 'legacy.db'}"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.attributes["database_url"] = url
    command.upgrade(config, "2cf3a3fb0c41")
    engine = make_engine(url)
    with session_factory(engine)() as session:
        session.add(TargetEvidence(target_id="ENSG00000169174", target_symbol="PCSK9",
                                   disease_id="TEST", disease_name="Preserve me",
                                   association_score=0.5, source_url="https://example.test"))
        session.commit()
    with engine.begin() as connection:
        connection.execute(text("""INSERT INTO experiments
            (created_at, target_id, data_source, model_kind, activity_type, threshold_pchembl,
             n_molecules, n_scaffolds, metrics, dataset_hash, artifact_path)
            VALUES ('2026-10-14 00:00:00', 'CHEMBL2929', 'synthetic_fixture', 'legacy', 'IC50',
                    6.0, 24, 8, '{}', 'legacy-hash', '/tmp/legacy.joblib')"""))
        connection.execute(text("DROP TABLE alembic_version"))
    init_db(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == ScriptDirectory.from_config(config).get_current_head()
        assert connection.execute(text("SELECT disease_name FROM target_evidence")).scalar_one() == "Preserve me"
        legacy_id = connection.execute(text("SELECT dataset_version_id FROM experiments")).scalar_one()
        assert legacy_id > 0
        assert connection.execute(text("SELECT status FROM dataset_versions WHERE id = :id"),
                                  {"id": legacy_id}).scalar_one() == "legacy_unverified"
        indexes = {item["name"] for item in inspect(connection).get_indexes("measurements")}
        assert "ix_measurements_source_target_type" in indexes
    with session_factory(engine)() as session:
        version = session.get(DatasetVersion, legacy_id)
        verify_version(version)
        report = experiment_report(session.scalar(select(Experiment)), version)
        assert report["dataset_version"]["status"] == "legacy_unverified"
        assert any("original snapshot" in note for note in report["limitations"])


def test_training_uses_stored_dataset_version_after_source_rows_change(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'history.db'}", str(tmp_path / "artifacts"))
    with TestClient(app) as client:
        assert client.post("/fixtures/load").status_code == 200
        first = client.post("/experiments", json={"source": "synthetic_fixture"}).json()
        version_id = first["dataset_version_id"]
        engine = make_engine(f"sqlite:///{tmp_path / 'history.db'}")
        with session_factory(engine)() as session:
            session.query(Measurement).filter(Measurement.source == "synthetic_fixture").delete()
            session.commit()
        second = client.post("/experiments", json={"source": "synthetic_fixture",
                                                   "dataset_version_id": version_id})
        assert second.status_code == 200, second.text
        assert second.json()["dataset_version_id"] == version_id
        assert second.json()["dataset_hash"] == first["dataset_hash"]
        assert second.json()["metrics"] == first["metrics"]
        assert client.get("/experiments").json()[0]["dataset_version_id"] == version_id
        with session_factory(engine)() as session:
            assert session.scalar(select(Experiment).order_by(Experiment.id.desc())).dataset_version_id == version_id


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://example/db")
    with pytest.raises(ValidationError):
        Settings(database_url="not-a-url")
    with pytest.raises(ValidationError):
        Settings(http_max_retries=-1)
