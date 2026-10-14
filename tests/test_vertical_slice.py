import httpx
import pytest
from types import SimpleNamespace
from pathlib import Path
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, select, text

from cvti.api import create_app
from cvti.chemistry import standardize
from cvti.config import Settings
from cvti.db import init_db, make_engine, session_factory
from cvti.ingest import SourceUnavailable, ingest_live, request_json
from cvti.models import Measurement, TargetEvidence
from cvti.ml import _examples


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
        assert data["metrics"]["scaffold_overlap"] == 0
        assert data["metrics"]["molecule_overlap"] == 0
        assert data["metrics"]["n_test_scaffolds"] > 0
        prediction = client.post("/predict", json={"smiles": "CC1CCCCC1"})
        assert prediction.status_code == 200, prediction.text
        assert 0 <= prediction.json()["probability_exploratory_activity"] <= 1
        assert prediction.json()["label"].startswith("Research hypothesis")
        assert client.get("/summary").json()["predictions"] == 1
        assert client.get("/evidence").json()[0]["disease_id"].startswith("SYNTHETIC")


def test_standardization_and_invalid_molecule():
    assert standardize("[Na+].O=C([O-])c1ccccc1")[0] == "O=C(O)c1ccccc1"
    with pytest.raises(ValueError):
        standardize("not a smiles")


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
        connection.execute(text("DROP TABLE alembic_version"))
    init_db(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == "0b0d802d3cb4"
        assert connection.execute(text("SELECT disease_name FROM target_evidence")).scalar_one() == "Preserve me"
        indexes = {item["name"] for item in inspect(connection).get_indexes("measurements")}
        assert "ix_measurements_source_target_type" in indexes


def test_invalid_configuration_is_rejected():
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://example/db")
    with pytest.raises(ValidationError):
        Settings(database_url="not-a-url")
    with pytest.raises(ValidationError):
        Settings(http_max_retries=-1)
