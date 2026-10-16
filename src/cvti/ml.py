"""A deliberately small, auditable IC50 classification baseline."""
import hashlib
import json
import os
from uuid import uuid4
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, balanced_accuracy_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import GroupShuffleSplit
from sqlalchemy import select

from cvti.chemistry import fingerprint, standardize
from cvti.config import get_settings
from cvti.training_provenance import capture_provenance, file_sha256, verify_artifact
from cvti.ingest import TARGET_CHEMBL
from cvti.models import PREDICTION_LABEL, DatasetVersion, Experiment, Measurement, Prediction
from cvti.provenance import (canonical_bytes, code_hashes, create_version,
                             measurement_records, verify_version, version_rows)


THRESHOLD = 6.0  # IC50 <= 1 micromolar, only an illustrative research label
EVALUATION_SPLITS = 5
SPLIT_ATTEMPTS = 500


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


def _class_counts(labels: np.ndarray) -> dict[str, int]:
    return {"inactive": int(np.sum(labels == 0)), "active": int(np.sum(labels == 1))}


def _evaluation_splits(X: np.ndarray, y: np.ndarray, groups: np.ndarray):
    """Take the first distinct, class-valid scaffold holdouts from a fixed sequence."""
    selected = []
    seen_test_groups = set()
    attempted = 0
    rejected_single_class = 0
    rejected_duplicate = 0
    splitter = GroupShuffleSplit(n_splits=SPLIT_ATTEMPTS, test_size=0.25, random_state=42)
    for train_idx, test_idx in splitter.split(X, y, groups):
        attempted += 1
        if len(set(y[train_idx])) != 2 or len(set(y[test_idx])) != 2:
            rejected_single_class += 1
            continue
        test_groups = frozenset(groups[test_idx])
        if test_groups in seen_test_groups:
            rejected_duplicate += 1
            continue
        seen_test_groups.add(test_groups)
        selected.append((train_idx, test_idx))
        if len(selected) == EVALUATION_SPLITS:
            break
    if len(selected) < EVALUATION_SPLITS:
        raise ValueError(f"Need {EVALUATION_SPLITS} distinct scaffold splits with both classes; "
                         f"found {len(selected)} in {attempted} attempts")
    return selected, {"attempted": attempted, "rejected_single_class": rejected_single_class,
                      "rejected_duplicate_partition": rejected_duplicate}


def _metric_summary(results: list[dict], name: str) -> dict[str, float]:
    values = [item[name] for item in results]
    return {"median": float(np.median(values)), "min": float(min(values)), "max": float(max(values))}


def train(session, source: str = "synthetic_fixture", artifact_dir: str | None = None,
          dataset_version_id: int | None = None, *, protocol_id: int | None = None,
          model_kind: str = "random_forest", project_id: int = 1) -> Experiment:
    from cvti.models import Project
    if session.get(Project, project_id) is None:
        raise ValueError('Project not found')
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
    from cvti.evaluation import prepare_protocol, classification_metrics
    protocol, examples, X, y, groups, splits, conflicts = prepare_protocol(session, version, protocol_id=protocol_id)
    split_selection = protocol.protocol_json['split_selection']
    def new_model():
        if model_kind == 'random_forest':
            return RandomForestClassifier(n_estimators=150, class_weight='balanced', random_state=42, n_jobs=1)
        if model_kind == 'logistic_regression':
            from sklearn.linear_model import LogisticRegression
            return LogisticRegression(C=1.0, class_weight='balanced', solver='liblinear', max_iter=1000, random_state=42)
        if model_kind == 'dummy':
            from sklearn.dummy import DummyClassifier
            return DummyClassifier(strategy='prior', random_state=42)
        raise ValueError('Unknown baseline model kind')
    split_results = []
    for split_number, (train_idx, test_idx) in enumerate(splits, start=1):
        train_scaffolds = set(groups[train_idx])
        test_scaffolds = set(groups[test_idx])
        train_smiles = {examples[i][0] for i in train_idx}
        test_smiles = {examples[i][0] for i in test_idx}
        scaffold_overlap = len(train_scaffolds & test_scaffolds)
        molecule_overlap = len(train_smiles & test_smiles)
        if scaffold_overlap or molecule_overlap:
            raise ValueError("Scaffold split leaked training molecules or scaffolds into the test set")
        evaluation_model = new_model()
        evaluation_model.fit(X[train_idx], y[train_idx])
        probabilities = evaluation_model.predict_proba(X[test_idx])[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        tn, fp, fn, tp = (int(value) for value in confusion_matrix(
            y[test_idx], predictions, labels=[0, 1]).ravel())
        train_bits, test_bits = X[train_idx].astype(bool), X[test_idx].astype(bool)
        nearest_similarities = []
        for bits in test_bits:
            intersection = np.logical_and(train_bits, bits).sum(axis=1)
            union = np.logical_or(train_bits, bits).sum(axis=1)
            nearest_similarities.append(float(np.max(np.divide(intersection, union, out=np.ones_like(intersection, dtype=float), where=union != 0))))
        similarity_errors = []
        for low, high in [(0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)]:
            mask = np.array([low <= value < high for value in nearest_similarities])
            if mask.any():
                similarity_errors.append({'lower': low, 'upper': min(high, 1.0), 'n': int(mask.sum()),
                                          'error_fraction': float(np.mean(predictions[mask] != y[test_idx][mask]))})
        split_results.append({
            "split": split_number,
            "train_smiles": sorted(train_smiles), "test_smiles": sorted(test_smiles),
            "fingerprint_overlap": protocol.protocol_json['splits'][split_number - 1]['fingerprint_overlap'],
            "source_document_overlap": protocol.protocol_json['splits'][split_number - 1]['source_document_overlap'],
            **classification_metrics(y[test_idx], probabilities),
            "error_by_training_similarity": similarity_errors,
            "test_predictions": [{'canonical_smiles': examples[i][0], 'scaffold': examples[i][1],
                                  'label': int(y[i]), 'score': float(score), 'nearest_training_similarity': similarity,
                                  'assay_ids': sorted({r['assay_id'] for r in version.records_json
                                                       if r['canonical_smiles'] == examples[i][0] and r.get('assay_id')})}
                                 for i, score, similarity in zip(test_idx, probabilities, nearest_similarities)],
            "train_class_counts": _class_counts(y[train_idx]),
            "test_class_counts": _class_counts(y[test_idx]),
            "n_train_scaffolds": len(train_scaffolds), "n_test_scaffolds": len(test_scaffolds),
            "test_scaffold_sha256": hashlib.sha256(
                json.dumps(sorted(test_scaffolds)).encode("utf-8")).hexdigest(),
            "scaffold_overlap": scaffold_overlap, "molecule_overlap": molecule_overlap,
            "balanced_accuracy": float(balanced_accuracy_score(y[test_idx], predictions)),
            "roc_auc": float(roc_auc_score(y[test_idx], probabilities)),
            "average_precision": float(average_precision_score(y[test_idx], probabilities)),
            "confusion_matrix": {"tn": tn, "fp": fp, "fn": fn, "tp": tp},
        })
    metrics = {
        "class_counts": _class_counts(y),
        "conflicting_molecules_excluded": conflicts,
        "label_note": "pChEMBL IC50 >= 6 (<=1 uM); exploratory research label",
        "evaluation": {
            "method": "five_distinct_scaffold_group_shuffle_holdouts",
            "test_fraction": 0.25, "random_state": 42,
            "split_selection": split_selection,
            "summary": {name: _metric_summary(split_results, name) for name in
                        ("balanced_accuracy", "roc_auc", "average_precision")},
            "splits": split_results,
            "caveat": "Repeated holdouts overlap and are not independent confidence intervals; no external validation",
        },
        "saved_model": "refit_on_all_version_molecules_after_evaluation",
    }
    model = new_model()
    model.fit(X, y)
    train_smiles = {example[0] for example in examples}
    train_scaffolds = set(groups)
    dataset_hash = hashlib.sha256(json.dumps(examples, sort_keys=True).encode()).hexdigest()
    metrics['evaluation']['protocol_id'] = protocol.id
    metrics['evaluation']['protocol_sha256'] = protocol.manifest_sha256
    run = Experiment(project_id=project_id, dataset_version_id=version.id, target_id=TARGET_CHEMBL,
                     data_source=source, model_kind={"random_forest": "Morgan2048_RF150", "logistic_regression": "Morgan2048_LR", "dummy": "DummyPrior"}[model_kind],
                     protocol_id=protocol.id,
                     activity_type="IC50", threshold_pchembl=THRESHOLD,
                     n_molecules=len(examples), n_scaffolds=len(set(groups)),
                     metrics=metrics, dataset_hash=dataset_hash, artifact_path="")
    session.add(run)
    session.flush()
    run.provenance_json = {**capture_provenance(), 'model_parameters': model.get_params(),
                           'protocol_id': protocol.id, 'protocol_sha256': protocol.manifest_sha256}
    directory = Path(artifact_dir or get_settings().artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"experiment-{run.id}.joblib"
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        joblib.dump({"model": model, "train_smiles": sorted(train_smiles),
                     "train_scaffolds": sorted(train_scaffolds), "dataset_hash": dataset_hash,
                     "dataset_version_id": version.id, "manifest_sha256": version.manifest_sha256}, temporary)
        run.artifact_sha256 = file_sha256(temporary)
        os.replace(temporary, path)
        run.artifact_path = str(path.resolve())
        session.commit()
    except Exception:
        session.rollback()
        temporary.unlink(missing_ok=True)
        path.unlink(missing_ok=True)
        raise
    return run


def predict(session, smiles: str, experiment_id: int | None = None, *, save: bool = True, project_id: int = 1) -> dict:
    from cvti.models import Project
    if session.get(Project, project_id) is None:
        raise ValueError('Project not found')
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
    artifact = verify_artifact(run)
    bundle = joblib.load(artifact)  # only artifacts written by this application
    if bundle["dataset_hash"] != run.dataset_hash:
        raise ValueError("Model artifact does not match experiment record")
    if version.status != "legacy_unverified" and (
        bundle.get("dataset_version_id") != version.id
        or bundle.get("manifest_sha256") != version.manifest_sha256
    ):
        raise ValueError("Model artifact does not match dataset version")
    probability = float(bundle["model"].predict_proba(fingerprint(canonical).reshape(1, -1))[0, 1])
    prediction_id = None
    if save:
        record = Prediction(project_id=project_id, experiment_id=run.id, input_smiles=smiles, canonical_smiles=canonical,
                            probability=probability)
        session.add(record)
        session.commit()
        prediction_id = record.id
    from cvti.evaluation import nearest_compounds
    latest_version_id = session.scalar(select(DatasetVersion.id).where(
        DatasetVersion.source == run.data_source).order_by(DatasetVersion.id.desc()))
    return {"prediction_id": prediction_id,
        "nearest_training_compounds": nearest_compounds(canonical, version, bundle['train_smiles']),
        "applicability_notice": "Similarity is structural context only; no validated applicability threshold",
        "calibration_status": "uncalibrated",
        "artifact_integrity": "verified" if run.artifact_sha256 else "legacy_unverified", "experiment_id": run.id, "canonical_smiles": canonical,
            "probability_exploratory_activity": probability, "label": PREDICTION_LABEL,
            "source": run.data_source, "seen_in_training": canonical in bundle["train_smiles"],
            "scaffold_seen_in_training": scaffold in bundle["train_scaffolds"],
            "dataset_version_id": version.id, "dataset_version_status": version.status,
            "dataset_version_superseded": version.id != latest_version_id,
            "manifest_sha256": version.manifest_sha256}
