"""A deliberately small, auditable IC50 classification baseline."""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import balanced_accuracy_score, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sqlalchemy import select

from cvti.chemistry import fingerprint, standardize
from cvti.config import get_settings
from cvti.ingest import TARGET_CHEMBL
from cvti.models import DatasetVersion, Experiment, Measurement, Prediction
from cvti.provenance import (canonical_bytes, code_hashes, create_version,
                             measurement_records, verify_version, version_rows)


THRESHOLD = 6.0  # IC50 <= 1 micromolar, only an illustrative research label


def _examples(rows):
    by_smiles = {}
    for row in rows:
        by_smiles.setdefault(row.canonical_smiles, []).append(row)
    examples = []
    conflicts = 0
    for smiles, records in sorted(by_smiles.items()):
        values = [r.pchembl_value for r in records]
        if min(values) < THRESHOLD <= max(values):
            conflicts += 1
            continue
        examples.append((smiles, records[0].scaffold, float(np.median(values))))
    return examples, conflicts


def train(session, source: str = "synthetic_fixture", artifact_dir: str | None = None,
          dataset_version_id: int | None = None) -> Experiment:
    if source not in {"synthetic_fixture", "chembl_curated"}:
        raise ValueError("Train only on the synthetic fixture or manually reviewed ChEMBL records")
    if dataset_version_id is not None:
        version = session.get(DatasetVersion, dataset_version_id)
        if version is None or version.source != source:
            raise ValueError("Dataset version does not match the requested source")
    elif source == "chembl_curated":
        version = session.scalar(select(DatasetVersion).where(
            DatasetVersion.source == source).order_by(DatasetVersion.id.desc()))
        if version is None:
            raise ValueError("No reviewed ChEMBL dataset version exists")
    else:
        current_rows = session.scalars(select(Measurement).where(
            Measurement.source == source, Measurement.target_id == TARGET_CHEMBL,
            Measurement.activity_type == "IC50"
        )).all()
        records = measurement_records(current_rows)
        snapshot = canonical_bytes({"kind": "synthetic_database_rows", "records": records})
        version = create_version(session, source=source, status="ready", target_id=TARGET_CHEMBL,
                                 endpoint_group=None, snapshot_blob=snapshot, review_blob=None,
                                 policy={"name": "synthetic_demo", "version": 1,
                                         "notice": "Synthetic data only; no biological interpretation",
                                         "implementation_sha256": code_hashes("ml.py", "chemistry.py", "ingest.py")},
                                 records=records, stats={"rows": len(records), "synthetic": True})
    if version.status != "ready":
        raise ValueError(f"Dataset version {version.id} is {version.status}; no model may be trained from it")
    rows = version_rows(version)
    examples, conflicts = _examples(rows)
    if len(examples) < 12 or len({x[1] for x in examples}) < 5:
        raise ValueError("Need at least 12 distinct molecules across 5 ring scaffolds")
    y = np.array([int(x[2] >= THRESHOLD) for x in examples])
    if len(set(y)) != 2:
        raise ValueError("Need both IC50 label classes")
    groups = np.array([x[1] for x in examples])
    X = np.stack([fingerprint(x[0]) for x in examples])
    split = None
    for train_idx, test_idx in GroupShuffleSplit(n_splits=100, test_size=0.25, random_state=42).split(X, y, groups):
        if len(set(y[train_idx])) == 2 and len(set(y[test_idx])) == 2:
            split = train_idx, test_idx
            break
    if split is None:
        raise ValueError("Unable to make a scaffold-disjoint split with both classes")
    train_idx, test_idx = split
    train_scaffolds = set(groups[train_idx])
    test_scaffolds = set(groups[test_idx])
    train_smiles = {examples[i][0] for i in train_idx}
    test_smiles = {examples[i][0] for i in test_idx}
    assert train_scaffolds.isdisjoint(test_scaffolds)
    assert train_smiles.isdisjoint(test_smiles)

    model = RandomForestClassifier(n_estimators=150, class_weight="balanced", random_state=42, n_jobs=1)
    model.fit(X[train_idx], y[train_idx])
    probabilities = model.predict_proba(X[test_idx])[:, 1]
    metrics = {
        "balanced_accuracy": float(balanced_accuracy_score(y[test_idx], probabilities >= 0.5)),
        "roc_auc": float(roc_auc_score(y[test_idx], probabilities)),
        "n_train": len(train_idx), "n_test": len(test_idx),
        "n_train_scaffolds": len(train_scaffolds), "n_test_scaffolds": len(test_scaffolds),
        "scaffold_overlap": 0, "molecule_overlap": 0,
        "conflicting_molecules_excluded": conflicts,
        "label_note": "pChEMBL IC50 >= 6 (<=1 uM); exploratory research label",
    }
    dataset_hash = hashlib.sha256(json.dumps(examples, sort_keys=True).encode()).hexdigest()
    run = Experiment(dataset_version_id=version.id, target_id=TARGET_CHEMBL,
                     data_source=source, model_kind="Morgan2048_RF150",
                     activity_type="IC50", threshold_pchembl=THRESHOLD,
                     n_molecules=len(examples), n_scaffolds=len(set(groups)),
                     metrics=metrics, dataset_hash=dataset_hash, artifact_path="")
    session.add(run)
    session.flush()
    directory = Path(artifact_dir or get_settings().artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"experiment-{run.id}.joblib"
    joblib.dump({"model": model, "train_smiles": sorted(train_smiles),
                "train_scaffolds": sorted(train_scaffolds), "dataset_hash": dataset_hash,
                "dataset_version_id": version.id, "manifest_sha256": version.manifest_sha256}, path)
    run.artifact_path = str(path.resolve())
    session.commit()
    return run


def predict(session, smiles: str, experiment_id: int | None = None) -> dict:
    query = select(Experiment).order_by(Experiment.id.desc())
    if experiment_id is not None:
        query = query.where(Experiment.id == experiment_id)
    run = session.scalar(query)
    if run is None:
        raise ValueError("Train a model first")
    version = session.get(DatasetVersion, run.dataset_version_id)
    if version is None:
        raise ValueError("Experiment dataset version is missing")
    verify_version(version)
    canonical, scaffold = standardize(smiles)
    bundle = joblib.load(run.artifact_path)  # only artifacts written by this application
    if bundle["dataset_hash"] != run.dataset_hash:
        raise ValueError("Model artifact does not match experiment record")
    if version.status != "legacy_unverified" and (
        bundle.get("dataset_version_id") != version.id
        or bundle.get("manifest_sha256") != version.manifest_sha256
    ):
        raise ValueError("Model artifact does not match dataset version")
    probability = float(bundle["model"].predict_proba(fingerprint(canonical).reshape(1, -1))[0, 1])
    record = Prediction(experiment_id=run.id, input_smiles=smiles, canonical_smiles=canonical,
                        probability=probability)
    session.add(record)
    session.commit()
    latest_version_id = session.scalar(select(DatasetVersion.id).where(
        DatasetVersion.source == run.data_source).order_by(DatasetVersion.id.desc()))
    return {"prediction_id": record.id, "experiment_id": run.id, "canonical_smiles": canonical,
            "probability_exploratory_activity": probability, "label": record.label,
            "source": run.data_source, "seen_in_training": canonical in bundle["train_smiles"],
            "scaffold_seen_in_training": scaffold in bundle["train_scaffolds"],
            "dataset_version_id": version.id, "dataset_version_status": version.status,
            "dataset_version_superseded": version.id != latest_version_id,
            "manifest_sha256": version.manifest_sha256}
