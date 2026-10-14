import csv
import json

import httpx
import pytest
from sqlalchemy import func, select

from cvti.curation import activity_issue, curate_snapshot, fetch_snapshot, write_review_sheet
from cvti.config import Settings
from cvti.db import init_db, make_engine, session_factory
from cvti.ml import train
from cvti.models import DatasetVersion, Measurement
from cvti.provenance import verify_version, version_rows
from cvti.reports import assay_reviews


def activity(activity_id, assay_id="CHEMBL_A", **changes):
    row = {"activity_id": activity_id, "target_chembl_id": "CHEMBL2929",
           "target_organism": "Homo sapiens", "standard_type": "IC50", "standard_relation": "=",
           "standard_units": "nM", "standard_flag": 1, "standard_value": "100",
           "pchembl_value": "7.00", "canonical_smiles": "Oc1ccccc1",
           "potential_duplicate": 0, "data_validity_comment": None,
           "molecule_chembl_id": f"CHEMBL_M{activity_id}", "assay_chembl_id": assay_id}
    return {**row, **changes}


def assay(assay_id="CHEMBL_A", **changes):
    return {"assay_chembl_id": assay_id, "target_chembl_id": "CHEMBL2929",
            "relationship_type": "D", "confidence_score": 9, "assay_type": "B",
            "description": "Reviewed biochemical PCSK9 binding readout", "bao_format": "BAO_TEST", **changes}


def test_quality_rules_are_explicit():
    assert activity_issue(activity(1)) is None
    assert activity_issue(activity(1, standard_value="10000")) == "invalid_or_inconsistent_pchembl"
    assert activity_issue(activity(1, target_organism=None)) == "wrong_or_unknown_human_target"
    assert activity_issue(activity(1, data_validity_comment="Potential author error")) == "data_validity_flag"
    assert activity_issue(activity(1, data_validity_comment="Manually validated")) is None
    assert activity_issue(activity(1, potential_duplicate=1)) == "potential_duplicate"


def test_review_gate_and_curation_report(tmp_path):
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"schema_version": 1, "target_chembl_id": "CHEMBL2929",
                                    "activities": [activity(1), activity(2, "CHEMBL_B"),
                                                   activity(3, standard_relation=">"),
                                                   activity(4, standard_value="10000"),
                                                   activity(5, "CHEMBL_C")],
                                    "assays": [assay(), assay("CHEMBL_B", confidence_score=8,
                                                               relationship_type="H"), assay("CHEMBL_C")]}))
    review = tmp_path / "review.csv"
    assert write_review_sheet(snapshot, review)["assays_with_activities"] == 3
    engine = make_engine(f"sqlite:///{tmp_path / 'curated.db'}")
    init_db(engine)
    with session_factory(engine)() as session:
        result = curate_snapshot(session, snapshot, review)
        assert result["inserted_measurements"] == 0
        assert result["applied"] is False
        assert result["status"] == "pending_review"
        pending_version = session.get(DatasetVersion, result["dataset_version_id"])
        assert pending_version.snapshot_blob == snapshot.read_bytes()
        assert pending_version.review_blob == review.read_bytes()
        assert result["excluded_by_reason"]["assay_not_approved"] == 2

    with review.open(newline="") as file:
        rows = list(csv.DictReader(file))
    rows[0]["decision"] = "include"
    with review.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with session_factory(engine)() as session:
        with pytest.raises(ValueError, match="review_note"):
            curate_snapshot(session, snapshot, review)

    rows[0]["review_note"] = "Reviewed assay description and primary source; direct protein binding."
    with review.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with session_factory(engine)() as session:
        with pytest.raises(ValueError, match="endpoint_group"):
            curate_snapshot(session, snapshot, review)

    rows[0]["endpoint_group"] = "pcsk9_ldlr_binding"
    rows[2]["decision"] = "exclude"
    with review.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with session_factory(engine)() as session:
        result = curate_snapshot(session, snapshot, review)
        first_version_id = result["dataset_version_id"]
        first_review_bytes = review.read_bytes()
        assert result["status"] == "ready"
        assert result["inserted_measurements"] == 1
        assert result["excluded_by_reason"]["indirect_or_low_confidence_target"] == 1
        assert result["excluded_by_reason"]["incompatible_endpoint"] == 1
        assert result["excluded_by_reason"]["invalid_or_inconsistent_pchembl"] == 1
        assert session.scalar(select(func.count()).select_from(Measurement)) == 1
        assert session.scalar(select(Measurement)).source == "chembl_curated"
        assert curate_snapshot(session, snapshot, review)["dataset_version_id"] == first_version_id
        assert session.scalar(select(func.count()).select_from(Measurement)) == 1
        first_version = session.get(DatasetVersion, first_version_id)
        verify_version(first_version)
        assert first_version.review_blob == review.read_bytes()
        assert first_version.policy_json["activity"]["type"] == "IC50"
        reviewed_assays = assay_reviews(first_version)
        assert reviewed_assays[0]["activity_exclusions"] == {
            "incompatible_endpoint": 1, "invalid_or_inconsistent_pchembl": 1}
        assert version_rows(first_version)[0].activity_id == "1"
        with pytest.raises(ValueError, match="manually reviewed"):
            train(session, "chembl")

    # A changed review replaces the curated source, so old approvals do not linger.
    rows[0]["decision"] = "exclude"
    rows[2]["decision"] = "include"
    rows[2]["endpoint_group"] = "pcsk9_ldlr_binding"
    rows[2]["review_note"] = "Independent review of direct binding readout."
    with review.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with session_factory(engine)() as session:
        result = curate_snapshot(session, snapshot, review)
        assert result["inserted_measurements"] == 1
        assert result["dataset_version_id"] != first_version_id
        assert session.scalar(select(Measurement)).source_record_id == "5"
        assert version_rows(session.get(DatasetVersion, first_version_id))[0].activity_id == "1"
        assert session.get(DatasetVersion, first_version_id).review_blob == first_review_bytes
        assert version_rows(session.get(DatasetVersion, result["dataset_version_id"]))[0].activity_id == "5"

    rows[2]["decision"] = "exclude"
    with review.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    with session_factory(engine)() as session:
        empty = curate_snapshot(session, snapshot, review)
        assert empty["status"] == "reviewed_empty"
        assert empty["applied"] is True
        assert session.scalar(select(func.count()).select_from(Measurement)) == 0
        assert version_rows(session.get(DatasetVersion, first_version_id))[0].activity_id == "1"
        with pytest.raises(ValueError, match="reviewed_empty"):
            train(session, "chembl_curated")


def test_snapshot_fetch_is_bounded_and_no_overwrite(tmp_path):
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if "activity.json" in str(request.url):
            return httpx.Response(200, json={"activities": [activity(1)], "page_meta": {"next": None}})
        return httpx.Response(200, json={"assays": [assay()], "page_meta": {"next": None}})

    path = tmp_path / "raw.json"
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_snapshot(path, Settings(chembl_max_records=2), client)
        assert result["activities"] == 1 and result["assays"] == 1
        assert len(calls) == 2
        with pytest.raises(ValueError, match="already exists"):
            fetch_snapshot(path, Settings(), client)
    assert json.loads(path.read_text())["activities"][0]["activity_id"] == 1
