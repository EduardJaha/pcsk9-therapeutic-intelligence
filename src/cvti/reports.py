"""Review views and portable reports built from preserved dataset versions."""

import csv
import io
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from cvti.models import DatasetVersion, Experiment
from cvti.provenance import verify_version, version_summary


RESEARCH_NOTICE = "Research hypotheses only; not validated drugs or evidence of therapeutic efficacy."


def assay_reviews(version: DatasetVersion) -> list[dict]:
    """Read recorded decisions; never rerun today's rules on historical inputs."""
    verify_version(version)
    if version.source != "chembl_curated" or version.snapshot_blob is None:
        return []
    snapshot = json.loads(version.snapshot_blob.decode("utf-8"))
    review = {}
    if version.review_blob is not None:
        review = {row["assay_chembl_id"]: row for row in csv.DictReader(
            io.StringIO(version.review_blob.decode("utf-8"), newline=""))}
    activities = snapshot.get("activities", [])
    counts = Counter(row.get("assay_chembl_id") or "unknown" for row in activities)
    selected = Counter(row.get("assay_id") for row in version.records_json)
    metadata = {row.get("assay_chembl_id"): row for row in snapshot.get("assays", [])}
    documents = defaultdict(set)
    for row in activities:
        if row.get("document_chembl_id"):
            documents[row.get("assay_chembl_id")].add(row["document_chembl_id"])
    results = []
    for assay_id, count in sorted(counts.items()):
        assay = metadata.get(assay_id, {})
        decision_row = review.get(assay_id, {})
        decision = decision_row.get("decision", "").strip().lower() or "pending"
        note = decision_row.get("review_note", "").strip()
        document_ids = set(documents[assay_id])
        if assay.get("document_chembl_id"):
            document_ids.add(assay["document_chembl_id"])
        for key in ("source_document_id", "document_chembl_ids"):
            document_ids.update(re.findall(r"CHEMBL\d+", decision_row.get(key, "")))
        outcome = version.stats_json.get("assay_outcomes", {}).get(assay_id, {})
        rule_reasons = outcome.get("excluded_by_reason", {})
        if decision == "exclude":
            reason = note or "Excluded by recorded review; no reviewer reason supplied"
        elif decision == "pending":
            reason = "Assay review decision is pending"
        elif version.status == "pending_review":
            reason = "Dataset review is pending; no training activities were retained in this version"
        elif not selected[assay_id]:
            reason = ("; ".join(f"{key}: {value}" for key, value in sorted(rule_reasons.items()))
                      or "No activities retained in this version; inspect its status and stored selection rules")
        else:
            reason = ""
        results.append({
            "assay_id": assay_id,
            "assay_url": f"https://www.ebi.ac.uk/chembl/assay_report_card/{assay_id}/" if assay_id != "unknown" else None,
            "source": "ChEMBL snapshot",
            "source_documents": [{"id": document_id,
                                  "url": f"https://www.ebi.ac.uk/chembl/document_report_card/{document_id}/"}
                                 for document_id in sorted(document_ids)],
            "description": assay.get("description", ""),
            "activity_count": count, "selected_activity_count": selected[assay_id],
            "decision": decision, "endpoint_group": decision_row.get("endpoint_group", ""),
            "review_note": note, "exclusion_reason": reason,
            "recorded_machine_issue": decision_row.get("machine_issue", ""),
            "activity_exclusions": rule_reasons,
        })
    return results


def render_assay_review_csv(rows: list[dict]) -> str:
    output = io.StringIO(newline="")
    fields = ["assay_id", "assay_url", "source", "source_documents", "decision", "endpoint_group",
              "activity_count", "selected_activity_count", "exclusion_reason", "review_note",
              "description", "recorded_machine_issue", "activity_exclusions"]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        values = {}
        for field in fields:
            value = row[field]
            if field == "source_documents":
                value = "; ".join(f"{doc['id']} {doc['url']}" for doc in value)
            elif field == "activity_exclusions":
                value = json.dumps(value, sort_keys=True)
            # Keep external descriptions and review text as text in spreadsheet apps.
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                value = "'" + value
            values[field] = value
        writer.writerow(values)
    return output.getvalue()


def experiment_report(run: Experiment, version: DatasetVersion) -> dict:
    verify_version(version)
    if (run.dataset_version_id != version.id or run.data_source != version.source
            or run.target_id != version.target_id):
        raise ValueError("Experiment and dataset version do not match")
    return {
        "report_schema_version": 2, "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_notice": RESEARCH_NOTICE,
        "experiment": {"id": run.id, "created_at": run.created_at.isoformat(),
                       "target_id": run.target_id, "source": run.data_source,
                       "model_kind": run.model_kind, "activity_type": run.activity_type,
                       "threshold_pchembl": run.threshold_pchembl,
                       "n_molecules": run.n_molecules, "n_scaffolds": run.n_scaffolds,
                       "dataset_hash": run.dataset_hash, "metrics": run.metrics,
                       "artifact_sha256": run.artifact_sha256,
                       "training_provenance": run.provenance_json,
                       "provenance_status": "recorded" if run.provenance_json else "legacy_unknown"},
        "dataset_version": {**version_summary(version), "selection_rules": version.policy_json},
        "assay_reviews": assay_reviews(version),
        "limitations": [
            "Synthetic fixture scores demonstrate software behavior only." if run.data_source == "synthetic_fixture"
            else "Assay review does not establish cross-assay comparability or therapeutic efficacy.",
            "Repeated scaffold holdouts overlap; their range is not an independent confidence interval.",
            "No independent or later dataset evaluation is recorded in this experiment.",
            *(["Legacy experiment: original snapshot, decisions and selected rows were not preserved."]
              if version.status == "legacy_unverified" else []),
        ],
    }


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def render_experiment_report(report: dict) -> str:
    run = report["experiment"]
    version = report["dataset_version"]
    metrics = run["metrics"]
    lines = [f"# PCSK9 research experiment {run['id']}", "", report["research_notice"], "",
             f"Generated: {report['generated_at']}", f"Experiment created: {run['created_at']}",
             f"Source: {run['source']}", f"Model: {run['model_kind']}",
             f"Molecules: {run['n_molecules']}; scaffolds: {run['n_scaffolds']}",
             f"Label: {run['activity_type']} pChEMBL >= {run['threshold_pchembl']}", "",
             "## Dataset provenance", "",
             f"Dataset version: {version['id']} ({version['status']})",
             f"Training examples SHA-256: {run['dataset_hash']}"]
    for name in ("manifest", "snapshot", "review", "policy", "records"):
        lines.append(f"{name.capitalize()} SHA-256: {version.get(name + '_sha256') or 'not recorded'}")
    lines += ["", "## Training provenance", "", "```json",
              json.dumps(run.get("training_provenance"), indent=2), "```",
              f"Model artifact SHA-256: {run.get('artifact_sha256') or 'unknown (legacy)'}",
              "", "## Evaluation", ""]
    if metrics.get("class_counts"):
        counts = metrics["class_counts"]
        lines.append(f"Dataset classes: inactive={counts['inactive']}, active={counts['active']}")
    evaluation = metrics.get("evaluation")
    if evaluation:
        lines += [evaluation["caveat"], "", "| Split | Train inactive/active | Test inactive/active | Balanced accuracy | ROC AUC | Average precision | Molecule/scaffold overlap |",
                  "|---|---|---|---|---|---|---|"]
        for row in evaluation["splits"]:
            train, test = row["train_class_counts"], row["test_class_counts"]
            lines.append(f"| {row['split']} | {train['inactive']}/{train['active']} | {test['inactive']}/{test['active']} | "
                         f"{row['balanced_accuracy']:.4f} | {row['roc_auc']:.4f} | {row['average_precision']:.4f} | "
                         f"{row['molecule_overlap']}/{row['scaffold_overlap']} |")
    else:
        lines.append("Older single-holdout evaluation; repeated split results are unavailable.")
    lines += ["", "Full recorded metrics:", "", "```json", json.dumps(metrics, indent=2), "```",
              "", "## Assay review", ""]
    if report["assay_reviews"]:
        lines += ["| Assay | Source documents | Decision | Selected activities | Exclusion reason / review note |",
                  "|---|---|---|---|---|"]
        for row in report["assay_reviews"]:
            sources = ", ".join(f"[{doc['id']}]({doc['url']})" for doc in row["source_documents"]) or "not recorded"
            assay_link = f"[{_cell(row['assay_id'])}]({row['assay_url']})" if row['assay_url'] else _cell(row['assay_id'])
            lines.append(f"| {assay_link} | {sources} | {_cell(row['decision'])} | "
                         f"{row['selected_activity_count']} | {_cell(row['exclusion_reason'] or row['review_note'])} |")
    else:
        lines.append("No ChEMBL assay review is associated with this experiment's dataset version.")
    lines += ["", "## Stored selection rules", "", "```json",
              json.dumps(version["selection_rules"], indent=2), "```", "", "## Limitations", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"
