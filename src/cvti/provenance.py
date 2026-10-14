"""Immutable in-database dataset manifests and integrity checks."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import select

from cvti.models import DatasetVersion, Measurement


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: bytes | object) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical_bytes(value)).hexdigest()


def code_hashes(*names: str) -> dict[str, str]:
    directory = Path(__file__).parent
    return {name: digest((directory / name).read_bytes()) for name in names}


def measurement_records(rows: list[Measurement]) -> list[dict]:
    return sorted(({
        "activity_id": row.source_record_id,
        "assay_id": row.assay_id,
        "molecule_id": row.molecule_id,
        "canonical_smiles": row.canonical_smiles,
        "scaffold": row.scaffold,
        "pchembl_value": row.pchembl_value,
    } for row in rows), key=lambda row: row["activity_id"])


def manifest_fields(*, source: str, status: str, target_id: str, endpoint_group: str | None,
                    snapshot_sha256: str | None, review_sha256: str | None,
                    policy_sha256: str, records_sha256: str, stats: dict) -> dict:
    return {"source": source, "status": status, "target_id": target_id,
            "endpoint_group": endpoint_group, "snapshot_sha256": snapshot_sha256,
            "review_sha256": review_sha256, "policy_sha256": policy_sha256,
            "records_sha256": records_sha256, "stats": stats}


def create_version(session, *, source: str, status: str, target_id: str, endpoint_group: str | None,
                   snapshot_blob: bytes | None, review_blob: bytes | None,
                   policy: dict, records: list[dict], stats: dict) -> DatasetVersion:
    snapshot_sha = digest(snapshot_blob) if snapshot_blob is not None else None
    review_sha = digest(review_blob) if review_blob is not None else None
    policy_sha = digest(policy)
    records_sha = digest(records)
    manifest_sha = digest(manifest_fields(
        source=source, status=status, target_id=target_id, endpoint_group=endpoint_group,
        snapshot_sha256=snapshot_sha, review_sha256=review_sha,
        policy_sha256=policy_sha, records_sha256=records_sha, stats=stats,
    ))
    existing = session.scalar(select(DatasetVersion).where(DatasetVersion.manifest_sha256 == manifest_sha))
    if existing:
        verify_version(existing)
        return existing
    version = DatasetVersion(source=source, status=status, target_id=target_id,
                             endpoint_group=endpoint_group, snapshot_sha256=snapshot_sha,
                             review_sha256=review_sha, policy_sha256=policy_sha,
                             records_sha256=records_sha, manifest_sha256=manifest_sha,
                             snapshot_blob=snapshot_blob, review_blob=review_blob,
                             policy_json=policy, records_json=records, stats_json=stats)
    session.add(version)
    session.flush()
    return version


def verify_version(version: DatasetVersion) -> None:
    if version.snapshot_sha256 != (digest(version.snapshot_blob) if version.snapshot_blob is not None else None):
        raise ValueError(f"Dataset version {version.id} snapshot integrity check failed")
    if version.review_sha256 != (digest(version.review_blob) if version.review_blob is not None else None):
        raise ValueError(f"Dataset version {version.id} review integrity check failed")
    if version.policy_sha256 != digest(version.policy_json) or version.records_sha256 != digest(version.records_json):
        raise ValueError(f"Dataset version {version.id} policy or records integrity check failed")
    fields = manifest_fields(source=version.source, status=version.status, target_id=version.target_id,
                             endpoint_group=version.endpoint_group, snapshot_sha256=version.snapshot_sha256,
                             review_sha256=version.review_sha256, policy_sha256=version.policy_sha256,
                             records_sha256=version.records_sha256, stats=version.stats_json)
    if version.manifest_sha256 != digest(fields):
        raise ValueError(f"Dataset version {version.id} manifest integrity check failed")


def version_rows(version: DatasetVersion) -> list[SimpleNamespace]:
    verify_version(version)
    return [SimpleNamespace(**row) for row in version.records_json]


def version_summary(version: DatasetVersion) -> dict:
    return {"id": version.id, "created_at": version.created_at.isoformat(), "source": version.source,
            "status": version.status, "target_id": version.target_id,
            "endpoint_group": version.endpoint_group,
            "snapshot_sha256": version.snapshot_sha256, "review_sha256": version.review_sha256,
            "policy_sha256": version.policy_sha256, "records_sha256": version.records_sha256,
            "manifest_sha256": version.manifest_sha256, "records": len(version.records_json),
            "stats": version.stats_json}
