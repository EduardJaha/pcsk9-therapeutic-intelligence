import csv
import io
import json

from fastapi.testclient import TestClient

from cvti.api import create_app
from cvti.db import make_engine, session_factory
from cvti.models import DatasetVersion, Experiment
from cvti.provenance import create_version
from cvti.reports import render_assay_review_csv


def test_review_and_report_use_experiment_history_and_check_integrity(tmp_path):
    url = f"sqlite:///{tmp_path / 'reports.db'}"
    with TestClient(create_app(url)) as client:
        with session_factory(make_engine(url))() as session:
            snapshot = json.dumps({
                "activities": [{"assay_chembl_id": "CHEMBL100", "document_chembl_id": "CHEMBL900"},
                               {"assay_chembl_id": "CHEMBL200", "document_chembl_id": "CHEMBL901"}],
                "assays": [{"assay_chembl_id": "CHEMBL100", "description": "Direct binding assay"},
                           {"assay_chembl_id": "CHEMBL200", "description": "Cellular expression assay",
                            "document_chembl_id": "CHEMBL902"}],
            }).encode()
            review = ("assay_chembl_id,decision,endpoint_group,review_note,source_document_id\n"
                      "CHEMBL100,include,pcsk9_ldlr_binding,Reviewed direct binding,CHEMBL900\n"
                      "CHEMBL200,exclude,,Cellular expression | different endpoint,CHEMBL903\n").encode()
            version = create_version(session, source="chembl_curated", status="ready",
                                     target_id="CHEMBL2929", endpoint_group="pcsk9_ldlr_binding",
                                     snapshot_blob=snapshot, review_blob=review,
                                     policy={"name": "original_rules"},
                                     records=[{"activity_id": "1", "assay_id": "CHEMBL100"}], stats={})
            run = Experiment(dataset_version_id=version.id, target_id="CHEMBL2929",
                             data_source="chembl_curated", model_kind="test_stub", activity_type="IC50",
                             threshold_pchembl=6, n_molecules=1, n_scaffolds=1,
                             metrics={"balanced_accuracy": 0.5, "roc_auc": 0.5},
                             dataset_hash="test_hash", artifact_path="not_needed_for_export")
            session.add(run)
            session.flush()
            run_id, version_id = run.id, version.id
            create_version(session, source="chembl_curated", status="reviewed_empty",
                           target_id="CHEMBL2929", endpoint_group="pcsk9_ldlr_binding",
                           snapshot_blob=snapshot,
                           review_blob=review.replace(b"Reviewed direct binding", b"Changed later review"),
                           policy={"name": "later_rules"}, records=[], stats={})
            session.commit()

        response = client.get(f"/dataset-versions/{version_id}/assays")
        assert response.status_code == 200
        included, excluded = response.json()["assays"]
        assert included["decision"] == "include" and included["selected_activity_count"] == 1
        assert excluded["decision"] == "exclude" and excluded["selected_activity_count"] == 0
        assert excluded["exclusion_reason"] == "Cellular expression | different endpoint"
        assert {doc["id"] for doc in excluded["source_documents"]} == {"CHEMBL901", "CHEMBL902", "CHEMBL903"}
        exported_rows = list(csv.DictReader(io.StringIO(render_assay_review_csv(response.json()["assays"]))))
        assert len(exported_rows) == 2
        assert exported_rows[1]["exclusion_reason"] == excluded["exclusion_reason"]
        assert "document_report_card/CHEMBL903" in exported_rows[1]["source_documents"]

        report = client.get(f"/experiments/{run_id}/report")
        assert report.status_code == 200
        assert report.json()["dataset_version"]["id"] == version_id
        assert report.json()["dataset_version"]["selection_rules"] == {"name": "original_rules"}
        assert report.json()["assay_reviews"][0]["review_note"] == "Reviewed direct binding"
        markdown = client.get(f"/experiments/{run_id}/report?format=markdown")
        assert markdown.status_code == 200
        assert markdown.headers["content-disposition"] == f'attachment; filename="experiment-{run_id}.md"'
        assert "document_report_card/CHEMBL903" in markdown.text
        assert "Cellular expression \\| different endpoint" in markdown.text
        assert "later_rules" not in markdown.text
        assert client.get("/experiments/999/report").status_code == 404
        assert client.get("/dataset-versions/999/assays").status_code == 404
        assert client.get(f"/experiments/{run_id}/report?format=bad").status_code == 422

        with session_factory(make_engine(url))() as session:
            session.get(DatasetVersion, version_id).snapshot_blob = b"tampered"
            session.commit()
        assert client.get(f"/dataset-versions/{version_id}/assays").status_code == 409
        assert client.get(f"/experiments/{run_id}/report").status_code == 409
