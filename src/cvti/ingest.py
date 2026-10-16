"""Bounded, retrying source ingestion with local provenance."""
import json
import random
import time
from pathlib import Path

import httpx
from sqlalchemy import select

from cvti.chemistry import standardize
from cvti.config import Settings, get_settings
from cvti.models import Measurement, TargetEvidence, utcnow


TARGET_CHEMBL = "CHEMBL2929"
TARGET_ENSEMBL = "ENSG00000169174"
RETRY_STATUS = {429, 500, 502, 503, 504}


class SourceUnavailable(RuntimeError):
    pass


def request_json(client: httpx.Client, method: str, url: str, settings: Settings, *, response_log=None, **kwargs) -> dict:
    for attempt in range(settings.http_max_retries + 1):
        try:
            response = client.request(method, url, timeout=settings.http_timeout_seconds, **kwargs)
            if response_log is not None:
                import base64
                import hashlib
                response_log.append({'method': method, 'url': str(response.request.url),
                                     'status_code': response.status_code,
                                     'body_base64': base64.b64encode(response.content).decode('ascii'),
                                     'sha256': hashlib.sha256(response.content).hexdigest()})
            if response.status_code in RETRY_STATUS:
                if attempt == settings.http_max_retries:
                    raise SourceUnavailable(f"{url}: HTTP {response.status_code} after retries")
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.replace(".", "", 1).isdigit() else settings.http_backoff_seconds * 2**attempt
                time.sleep(min(delay, 60) + random.uniform(0, 0.2))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise SourceUnavailable(f"{url}: HTTP {response.status_code}") from exc
            return response.json()
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            if attempt == settings.http_max_retries:
                raise SourceUnavailable(f"{url}: {exc}") from exc
            time.sleep(settings.http_backoff_seconds * 2**attempt)
    raise AssertionError("unreachable")


def _save_measurement(session, row: dict, source: str) -> bool:
    record_id = str(row["activity_id"])
    if session.scalar(select(Measurement.id).where(Measurement.source == source, Measurement.source_record_id == record_id)):
        return False
    if row.get("target_chembl_id") != TARGET_CHEMBL or row.get("standard_type") != "IC50":
        return False
    if row.get("standard_relation") != "=" or row.get("standard_units") != "nM":
        return False
    if row.get("data_validity_comment") not in (None, "Manually validated") or row.get("potential_duplicate") not in (None, 0, "0"):
        return False
    try:
        value = float(row["pchembl_value"])
        canonical, scaffold = standardize(row["canonical_smiles"])
    except (ValueError, TypeError, KeyError):
        return False
    if not 3 <= value <= 12:
        return False
    session.add(Measurement(
        source=source, source_record_id=record_id,
        source_url=f"https://www.ebi.ac.uk/chembl/compound_report_card/{row.get('molecule_chembl_id')}" if source.startswith("chembl") else None,
        target_id=TARGET_CHEMBL, molecule_id=row.get("molecule_chembl_id"),
        assay_id=row.get("assay_chembl_id"), raw_smiles=row["canonical_smiles"],
        canonical_smiles=canonical, scaffold=scaffold, activity_type="IC50", pchembl_value=value,
    ))
    return True


def ingest_fixture(session, path: Path | None = None) -> dict:
    if path is None:
        path = Path(__file__).parents[2] / "fixtures" / "pcsk9_synthetic.json"
        if not path.is_file():
            path = Path.cwd() / "fixtures" / "pcsk9_synthetic.json"
    payload = json.loads(path.read_text())
    count = 0
    for row in payload["activities"]:
        row = {"target_chembl_id": TARGET_CHEMBL, "standard_type": "IC50",
               "standard_relation": "=", "standard_units": "nM", **row}
        count += _save_measurement(session, row, "synthetic_fixture")
    for row in payload["diseases"]:
        _save_evidence(session, row)
    session.commit()
    return {"source": "synthetic_fixture", "inserted_measurements": count, "evidence_rows": len(payload["diseases"])}


def _save_evidence(session, row: dict) -> None:
    disease = row["disease"]
    existing = session.scalar(select(TargetEvidence).where(
        TargetEvidence.target_id == TARGET_ENSEMBL, TargetEvidence.disease_id == disease["id"]
    ))
    if existing:
        existing.association_score = float(row["score"])
        existing.retrieved_at = utcnow()
    else:
        session.add(TargetEvidence(
            target_id=TARGET_ENSEMBL, target_symbol="PCSK9", disease_id=disease["id"],
            disease_name=disease["name"], association_score=float(row["score"]),
            source_url=f"https://platform.opentargets.org/target/{TARGET_ENSEMBL}",
        ))


def ingest_live(session, settings: Settings | None = None, client: httpx.Client | None = None) -> dict:
    settings = settings or get_settings()
    own_client = client is None
    client = client or httpx.Client(headers={"User-Agent": "cvti-mvp/0.1 research"})
    inserted = 0
    scanned = 0
    try:
        base = settings.chembl_base_url.rstrip("/")
        offset = 0
        while scanned < settings.chembl_max_records:
            limit = min(100, settings.chembl_max_records - scanned)
            data = request_json(client, "GET", f"{base}/activity.json", settings, params={
                "target_chembl_id": TARGET_CHEMBL, "standard_type": "IC50",
                "standard_relation": "=", "standard_units": "nM",
                "pchembl_value__isnull": "false", "limit": limit, "offset": offset,
            })
            rows = data.get("activities", [])
            inserted += sum(_save_measurement(session, row, "chembl") for row in rows)
            scanned += len(rows)
            offset += len(rows)
            session.commit()  # keep completed pages if a later request fails
            if not rows or not data.get("page_meta", {}).get("next"):
                break

        query = """query PCSK9($id: String!){target(ensemblId:$id){id approvedSymbol associatedDiseases(page:{index:0,size:20}){rows{score disease{id name}}}}}"""
        data = request_json(client, "POST", settings.open_targets_graphql_url, settings,
                            json={"query": query, "variables": {"id": TARGET_ENSEMBL}})
        if data.get("errors") or not data.get("data", {}).get("target"):
            raise SourceUnavailable("Open Targets returned GraphQL errors or no PCSK9 target")
        target = data["data"]["target"]
        if target["id"] != TARGET_ENSEMBL or target["approvedSymbol"] != "PCSK9":
            raise SourceUnavailable("Open Targets returned an unexpected target")
        evidence = target["associatedDiseases"]["rows"]
        for row in evidence:
            _save_evidence(session, row)
        session.commit()
        return {"source": "live", "scanned_measurements": scanned,
                "inserted_measurements": inserted, "evidence_rows": len(evidence)}
    finally:
        if own_client:
            client.close()


def fetch_evidence_snapshot(path: Path, settings=None, client=None):
    """Preserve a bounded Open Targets context response, never as molecular labels."""
    import hashlib
    from datetime import datetime, timezone
    settings = settings or get_settings()
    if path.exists():
        raise ValueError('Evidence snapshot output already exists')
    own_client = client is None
    client = client or httpx.Client()
    responses = []
    started = datetime.now(timezone.utc).isoformat()
    query = 'query PCSK9($id:String!){target(ensemblId:$id){id approvedSymbol associatedDiseases(page:{index:0,size:20}){rows{score disease{id name}}}}}'
    try:
        payload = request_json(client, 'POST', settings.open_targets_graphql_url, settings, response_log=responses,
                               json={'query': query, 'variables': {'id': TARGET_ENSEMBL}})
        if payload.get('errors') or payload.get('data', {}).get('target', {}).get('id') != TARGET_ENSEMBL:
            raise SourceUnavailable('Open Targets evidence response is incomplete or target does not match')
        snapshot = {'schema_version': 1, 'source': 'Open Targets', 'purpose': 'context_only_not_training_labels',
                    'query': query, 'variables': {'id': TARGET_ENSEMBL}, 'source_release': None,
                    'retrieval_started_at': started, 'retrieval_completed_at': datetime.now(timezone.utc).isoformat(),
                    'completeness': 'bounded_sample', 'page': {'index': 0, 'size': 20}, 'responses': responses,
                    'data': payload['data']}
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as handle:
            json.dump(snapshot, handle, indent=2, sort_keys=True)
        return {'snapshot': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'completeness': 'bounded_sample', 'purpose': snapshot['purpose']}
    finally:
        if own_client:
            client.close()
