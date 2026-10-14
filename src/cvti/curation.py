"""Explicit, conservative ChEMBL IC50 curation for exploratory PCSK9 work."""

import csv
import hashlib
import io
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import delete, select

from cvti.chemistry import standardize
from cvti.config import Settings, get_settings
from cvti.ingest import TARGET_CHEMBL, _save_measurement, request_json
from cvti.models import Measurement
from cvti.provenance import code_hashes, create_version, measurement_records, version_summary


ENDPOINT_GROUP = "pcsk9_ldlr_binding"


def curation_policy() -> dict:
    """Record both the readable rules and hashes of their implementation."""
    return {
        "name": "pcsk9_ldlr_binding", "version": 1,
        "target_chembl_id": TARGET_CHEMBL, "target_organism": "Homo sapiens",
        "activity": {"type": "IC50", "relation": "=", "units": "nM", "standard_flag": 1,
                     "pchembl_min": 3, "pchembl_max": 12, "pchembl_tolerance": 0.1,
                     "validity_comments": [None, "Manually validated"], "exclude_potential_duplicates": True,
                     "require_molecule_assay_activity_ids": True, "require_ring_scaffold": True},
        "assay": {"relationship_type": "D", "confidence_score": 9, "assay_type": "B",
                  "require_description": True, "manual_endpoint_review": ENDPOINT_GROUP},
        "implementation_sha256": code_hashes("curation.py", "ingest.py", "chemistry.py"),
    }


def _pages(client: httpx.Client, url: str, key: str, settings: Settings, params: dict, cap: int | None = None) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while cap is None or len(rows) < cap:
        limit = min(100, cap - len(rows)) if cap is not None else 100
        data = request_json(client, "GET", url, settings, params={**params, "limit": limit, "offset": offset})
        page = data.get(key)
        if not isinstance(page, list):
            raise ValueError(f"ChEMBL response has no {key} list")
        rows.extend(page)
        offset += len(page)
        if not page or not data.get("page_meta", {}).get("next"):
            break
    return rows


def fetch_snapshot(path: Path, settings: Settings | None = None, client: httpx.Client | None = None) -> dict:
    """Save a bounded raw activity/assay snapshot; never overwrite an earlier pull."""
    settings = settings or get_settings()
    if path.exists():
        raise ValueError(f"Snapshot already exists: {path}")
    own_client = client is None
    client = client or httpx.Client(headers={"User-Agent": "cvti-mvp/0.1 research"})
    try:
        base = settings.chembl_base_url.rstrip("/")
        query = {"target_chembl_id": TARGET_CHEMBL, "standard_type": "IC50",
                 "standard_relation": "=", "standard_units": "nM", "pchembl_value__isnull": "false"}
        activities = _pages(client, f"{base}/activity.json", "activities", settings, query, settings.chembl_max_records)
        assays = _pages(client, f"{base}/assay.json", "assays", settings,
                        {"target_chembl_id": TARGET_CHEMBL})
        payload = {"schema_version": 1, "target_chembl_id": TARGET_CHEMBL,
                   "retrieved_at": datetime.now(timezone.utc).isoformat(), "chembl_base_url": base,
                   "activity_query": query, "activities": activities, "assays": assays}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
        return {"snapshot": str(path), "activities": len(activities), "assays": len(assays),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    finally:
        if own_client:
            client.close()


def _parse_snapshot(raw: bytes) -> dict:
    payload = json.loads(raw.decode("utf-8"))
    if (payload.get("schema_version") != 1 or payload.get("target_chembl_id") != TARGET_CHEMBL
            or not isinstance(payload.get("activities"), list) or not isinstance(payload.get("assays"), list)):
        raise ValueError("Snapshot is not a version 1 PCSK9 ChEMBL snapshot")
    return payload


def _load_snapshot(path: Path) -> dict:
    return _parse_snapshot(path.read_bytes())


def assay_issue(assay: dict) -> str | None:
    """Metadata gate. A pass still requires manual review of assay meaning."""
    if assay.get("target_chembl_id") != TARGET_CHEMBL:
        return "wrong_assay_target"
    if assay.get("relationship_type") != "D" or assay.get("confidence_score") != 9:
        return "indirect_or_low_confidence_target"
    if assay.get("assay_type") != "B":
        return "not_binding_assay"
    if not assay.get("description"):
        return "missing_assay_description"
    return None


def activity_issue(row: dict) -> str | None:
    if row.get("target_chembl_id") != TARGET_CHEMBL or row.get("target_organism") != "Homo sapiens":
        return "wrong_or_unknown_human_target"
    if row.get("standard_type") != "IC50" or row.get("standard_relation") != "=" or row.get("standard_units") != "nM":
        return "incompatible_endpoint"
    if row.get("standard_flag") not in (1, "1"):
        return "not_standardized"
    if row.get("data_validity_comment") not in (None, "Manually validated"):
        return "data_validity_flag"
    if row.get("potential_duplicate") not in (None, 0, "0"):
        return "potential_duplicate"
    if not row.get("activity_id") or not row.get("assay_chembl_id") or not row.get("molecule_chembl_id"):
        return "missing_provenance"
    try:
        pchembl = float(row["pchembl_value"])
        value_nm = float(row["standard_value"])
        if (not math.isfinite(pchembl) or not math.isfinite(value_nm) or value_nm <= 0
                or not 3 <= pchembl <= 12 or abs(pchembl - (9 - math.log10(value_nm))) > 0.1):
            return "invalid_or_inconsistent_pchembl"
        standardize(row["canonical_smiles"])
    except (KeyError, TypeError, ValueError):
        return "invalid_or_missing_structure_or_value"
    return None


def write_review_sheet(snapshot: Path, output: Path) -> dict:
    payload = _load_snapshot(snapshot)
    if output.exists():
        raise ValueError(f"Review sheet already exists: {output}")
    counts = Counter(row.get("assay_chembl_id") for row in payload["activities"])
    documents: dict[str, set[str]] = {}
    for row in payload["activities"]:
        if row.get("assay_chembl_id") and row.get("document_chembl_id"):
            documents.setdefault(row["assay_chembl_id"], set()).add(row["document_chembl_id"])
    assays = {row.get("assay_chembl_id"): row for row in payload["assays"]}
    output.parent.mkdir(parents=True, exist_ok=True)
    columns = ["assay_chembl_id", "assay_url", "document_chembl_ids", "activity_count", "machine_issue",
               "assay_type", "confidence_score", "relationship_type", "bao_format", "description",
               "decision", "endpoint_group", "review_note"]
    with output.open("x", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        for assay_id in sorted(counts, key=lambda value: str(value)):
            assay = assays.get(assay_id, {})
            writer.writerow({"assay_chembl_id": assay_id or "",
                             "assay_url": f"https://www.ebi.ac.uk/chembl/assay_report_card/{assay_id}/" if assay_id else "",
                             "document_chembl_ids": ", ".join(sorted(documents.get(assay_id, set()))),
                             "activity_count": counts[assay_id],
                             "machine_issue": assay_issue(assay) if assay else "missing_assay_metadata",
                             "assay_type": assay.get("assay_type"), "confidence_score": assay.get("confidence_score"),
                             "relationship_type": assay.get("relationship_type"), "bao_format": assay.get("bao_format"),
                             "description": assay.get("description"), "decision": "", "endpoint_group": "", "review_note": ""})
    return {"review_sheet": str(output), "assays_with_activities": len(counts),
            "instruction": f"Include only reviewed direct PCSK9-LDLR binding assays: decision=include, endpoint_group={ENDPOINT_GROUP}, and a review_note. Leave uncertain assays blank or exclude."}


def curate_snapshot(session, snapshot: Path, review_sheet: Path) -> dict:
    snapshot_blob = snapshot.read_bytes()
    review_blob = review_sheet.read_bytes()
    payload = _parse_snapshot(snapshot_blob)
    with io.StringIO(review_blob.decode("utf-8"), newline="") as file:
        reader = csv.DictReader(file)
        if not {"assay_chembl_id", "decision", "endpoint_group", "review_note"}.issubset(reader.fieldnames or []):
            raise ValueError("Review sheet needs assay_chembl_id, decision, endpoint_group, and review_note columns")
        review = {}
        for row in reader:
            assay_id = row["assay_chembl_id"].strip()
            decision = row["decision"].strip().lower()
            if not assay_id or assay_id in review or decision not in {"", "include", "exclude"}:
                raise ValueError("Review sheet has an empty/duplicate assay ID or invalid decision")
            if decision == "include" and not row["review_note"].strip():
                raise ValueError(f"Included assay {assay_id} needs a review_note")
            if decision == "include" and row["endpoint_group"].strip() != ENDPOINT_GROUP:
                raise ValueError(f"Included assay {assay_id} needs endpoint_group={ENDPOINT_GROUP}")
            review[assay_id] = decision
    activity_assay_ids = {row.get("assay_chembl_id") for row in payload["activities"]}
    if set(review) - activity_assay_ids:
        raise ValueError("Review sheet contains assay IDs absent from the snapshot")
    assays = {row.get("assay_chembl_id"): row for row in payload["assays"]}
    reasons = Counter()
    accepted = []
    candidate_assays = set()
    assay_outcomes = {}
    for row in payload["activities"]:
        outcome = assay_outcomes.setdefault(row.get("assay_chembl_id") or "unknown",
                                            {"approved_activity_rows": 0, "excluded_by_reason": Counter()})
        issue = activity_issue(row)
        if issue is None:
            assay_id = row["assay_chembl_id"]
            assay = assays.get(assay_id)
            issue = assay_issue(assay) if assay else "missing_assay_metadata"
            if issue is None:
                candidate_assays.add(assay_id)
                if review.get(assay_id) != "include":
                    issue = "assay_not_approved"
        if issue:
            reasons[issue] += 1
            outcome["excluded_by_reason"][issue] += 1
        else:
            accepted.append(row)
            outcome["approved_activity_rows"] += 1
    pending = sorted(assay_id for assay_id in candidate_assays if review.get(assay_id) not in {"include", "exclude"})
    status = "pending_review" if pending else "ready" if accepted else "reviewed_empty"
    inserted = 0
    records = []
    if status != "pending_review":
        # The measurement table is a current view. Immutable version records
        # retain old inputs when a later review replaces this view.
        session.execute(delete(Measurement).where(Measurement.source == "chembl_curated"))
        for row in accepted:
            inserted += _save_measurement(session, row, "chembl_curated")
        if inserted != len(accepted):
            raise ValueError("Curated import did not preserve every approved activity")
        session.flush()
        rows = session.scalars(select(Measurement).where(Measurement.source == "chembl_curated")).all()
        records = measurement_records(rows)
    stats = {"scanned": len(payload["activities"]), "approved_activity_rows": len(accepted),
             "excluded_by_reason": dict(sorted(reasons.items())), "pending_assays": pending,
             "snapshot_retrieved_at": payload.get("retrieved_at"),
             "assay_outcomes": {assay_id: {"approved_activity_rows": outcome["approved_activity_rows"],
                                            "excluded_by_reason": dict(sorted(outcome["excluded_by_reason"].items()))}
                                for assay_id, outcome in sorted(assay_outcomes.items())}}
    version = create_version(session, source="chembl_curated", status=status, target_id=TARGET_CHEMBL,
                             endpoint_group=ENDPOINT_GROUP, snapshot_blob=snapshot_blob,
                             review_blob=review_blob, policy=curation_policy(), records=records, stats=stats)
    session.commit()
    summary = version_summary(version)
    return {"source": "chembl_curated", "endpoint_group": ENDPOINT_GROUP,
            "dataset_version_id": version.id, "status": status,
            "manifest_sha256": summary["manifest_sha256"],
            "snapshot_sha256": summary["snapshot_sha256"],
            "review_sha256": summary["review_sha256"], "applied": status != "pending_review",
            "scanned": len(payload["activities"]), "approved_activity_rows": len(accepted),
            "inserted_measurements": inserted, "excluded_by_reason": dict(sorted(reasons.items()))}
