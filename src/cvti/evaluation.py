"""Frozen development protocols and separate scoring without refitting."""
import hashlib
import json
from types import SimpleNamespace

import joblib
import numpy as np
from sklearn.metrics import (average_precision_score, balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, log_loss, roc_auc_score)
from sqlalchemy import select

from cvti.chemistry import fingerprint
from cvti.models import DatasetVersion, EvaluationProtocol, Experiment, ExternalEvaluation
from cvti.provenance import digest, verify_version
from cvti.training_provenance import verify_artifact


def classification_metrics(labels, probabilities):
    predicted = (probabilities >= 0.5).astype(int)
    tn, fp, fn, tp = (int(v) for v in confusion_matrix(labels, predicted, labels=[0, 1]).ravel())
    reliability = []
    for index in range(5):
        low, high = index / 5, (index + 1) / 5
        mask = (probabilities >= low) & ((probabilities < high) if index < 4 else (probabilities <= high))
        if mask.any():
            reliability.append({'lower': low, 'upper': high, 'n': int(mask.sum()),
                                'mean_score': float(probabilities[mask].mean()), 'observed_fraction': float(labels[mask].mean())})
    return {'balanced_accuracy': float(balanced_accuracy_score(labels, predicted)),
            'roc_auc': float(roc_auc_score(labels, probabilities)),
            'average_precision': float(average_precision_score(labels, probabilities)),
            'positive_prevalence': float(labels.mean()), 'brier_score': float(brier_score_loss(labels, probabilities)),
            'log_loss': float(log_loss(labels, probabilities, labels=[0, 1])), 'reliability_bins': reliability,
            'confusion_matrix': {'tn': tn, 'fp': fp, 'fn': fn, 'tp': tp}}


def prepare_protocol(session, version, *, protocol_id=None):
    from cvti.ml import THRESHOLD, _examples, _evaluation_splits
    verify_version(version)
    if version.status != 'ready':
        raise ValueError(f'Dataset version {version.id} is {version.status}; cannot freeze a training protocol')
    examples, conflicts = _examples([SimpleNamespace(**row) for row in version.records_json])
    if len(examples) < 12 or len({row[1] for row in examples}) < 5:
        raise ValueError('Need at least 12 distinct molecules across 5 ring scaffolds')
    labels = np.array([int(row[2] >= THRESHOLD) for row in examples])
    if len(set(labels)) != 2:
        raise ValueError('Need both IC50 label classes')
    X = np.stack([fingerprint(row[0]) for row in examples])
    groups = np.array([row[1] for row in examples])
    fp_hashes = [hashlib.sha256(row.tobytes()).hexdigest() for row in X]
    documents = {}
    for row in version.records_json:
        if row.get('document_chembl_id'):
            documents.setdefault(row['canonical_smiles'], set()).add(row['document_chembl_id'])
    if protocol_id is not None:
        protocol = session.get(EvaluationProtocol, protocol_id)
        if protocol is None or protocol.dataset_version_id != version.id:
            raise ValueError('Protocol does not belong to this dataset version')
        if digest(protocol.protocol_json) != protocol.manifest_sha256:
            raise ValueError('Protocol integrity check failed')
        if protocol.protocol_json['dataset_manifest_sha256'] != version.manifest_sha256:
            raise ValueError('Protocol dataset manifest mismatch')
        if protocol.protocol_json['feature_matrix_sha256'] != hashlib.sha256(X.tobytes()).hexdigest():
            raise ValueError('Fingerprint implementation changed; create a new protocol and dataset policy')
        index = {row[0]: i for i, row in enumerate(examples)}
        assignments = [(np.array([index[s] for s in part['train_smiles']]),
                        np.array([index[s] for s in part['test_smiles']])) for part in protocol.protocol_json['splits']]
        return protocol, examples, X, labels, groups, assignments, conflicts
    assignments, selection = _evaluation_splits(X, labels, groups)
    splits = []
    for train, test in assignments:
        fp_overlap = set(fp_hashes[i] for i in train) & set(fp_hashes[i] for i in test)
        if fp_overlap:
            raise ValueError('Identical fingerprints cross a scaffold partition; dataset needs representation review')
        train_docs = set().union(*(documents.get(examples[i][0], set()) for i in train))
        test_docs = set().union(*(documents.get(examples[i][0], set()) for i in test))
        splits.append({'train_smiles': sorted(examples[i][0] for i in train),
                       'test_smiles': sorted(examples[i][0] for i in test), 'fingerprint_overlap': 0,
                       'source_document_overlap': sorted(train_docs & test_docs)})
    payload = {'schema_version': 1, 'dataset_manifest_sha256': version.manifest_sha256,
               'endpoint_group': version.endpoint_group, 'activity_threshold_pchembl': THRESHOLD,
               'classification_threshold': 0.5, 'feature_policy': {'kind': 'Morgan', 'bits': 2048, 'radius': 2, 'chirality': False},
               'feature_matrix_sha256': hashlib.sha256(X.tobytes()).hexdigest(), 'seed': 42,
               'split_selection': selection, 'splits': splits,
               'metrics': ['balanced_accuracy', 'roc_auc', 'average_precision', 'brier_score', 'log_loss'],
               'purpose': 'development_only', 'final_holdout': 'No independent final dataset reserved in this protocol',
               'source_overlap_policy': 'Recorded, not claimed source-independent; do not use holdouts as final external validation'}
    checksum = digest(payload)
    protocol = session.scalar(select(EvaluationProtocol).where(EvaluationProtocol.manifest_sha256 == checksum))
    if protocol is None:
        protocol = EvaluationProtocol(dataset_version_id=version.id, manifest_sha256=checksum, protocol_json=payload)
        session.add(protocol)
        session.flush()
    return protocol, examples, X, labels, groups, assignments, conflicts


def nearest_compounds(smiles, version, training_smiles, limit=5):
    from cvti.ml import THRESHOLD
    query = fingerprint(smiles).astype(bool)
    results = []
    for reference in training_smiles:
        features = fingerprint(reference).astype(bool)
        union = int(np.logical_or(query, features).sum())
        similarity = float(np.logical_and(query, features).sum() / union) if union else 1.0
        rows = [r for r in version.records_json if r['canonical_smiles'] == reference]
        values = [r['pchembl_value'] for r in rows]
        results.append({'canonical_smiles': reference, 'tanimoto_similarity': similarity,
                        'median_pchembl': float(np.median(values)) if values else None,
                        'activity_class': ('active' if np.median(values) >= THRESHOLD else 'inactive') if values else 'unknown',
                        'activity_ids': [r['activity_id'] for r in rows], 'assay_ids': sorted({r['assay_id'] for r in rows if r.get('assay_id')}),
                        'source_documents': sorted({r['document_chembl_id'] for r in rows if r.get('document_chembl_id')})})
    return sorted(results, key=lambda row: (-row['tanimoto_similarity'], row['canonical_smiles']))[:limit]


def evaluate_existing(session, experiment_id, dataset_version_id, *, mode='independent'):
    from cvti.ml import THRESHOLD, _examples
    run, version = session.get(Experiment, experiment_id), session.get(DatasetVersion, dataset_version_id)
    if run is None or version is None:
        raise ValueError('Experiment and evaluation dataset must exist')
    training = session.get(DatasetVersion, run.dataset_version_id)
    verify_version(training)
    verify_version(version)
    if version.id == training.id or version.status != 'ready':
        raise ValueError('Use a separate ready reviewed evaluation dataset')
    if (version.target_id, version.endpoint_group, version.source) != (training.target_id, training.endpoint_group, training.source):
        raise ValueError('Evaluation target, endpoint and source type must match training')
    if mode not in {'independent', 'later'}:
        raise ValueError('Evaluation mode must be independent or later')
    artifact = verify_artifact(run)
    bundle = joblib.load(artifact)
    if bundle.get('dataset_hash') != run.dataset_hash:
        raise ValueError('Model does not match experiment')
    examples, conflicts = _examples([SimpleNamespace(**row) for row in version.records_json])
    train_fp = {hashlib.sha256(fingerprint(s).tobytes()).hexdigest() for s in bundle['train_smiles']}
    kept = [row for row in examples if hashlib.sha256(fingerprint(row[0]).tobytes()).hexdigest() not in train_fp]
    train_docs = {r['document_chembl_id'] for r in training.records_json if r.get('document_chembl_id')}
    test_docs = {r['document_chembl_id'] for r in version.records_json if r.get('document_chembl_id')}
    overlap_docs = train_docs & test_docs
    if overlap_docs:
        raise ValueError('Evaluation shares source publications with training; obtain independently reviewed data')
    if mode == 'later':
        training_dates = [r.get('publication_date') for r in training.records_json]
        test_dates = [r.get('publication_date') for r in version.records_json]
        from datetime import date
        try:
            train_dates = [date.fromisoformat(d) for d in training_dates]
            later_dates = [date.fromisoformat(d) for d in test_dates]
            if not train_dates or not later_dates or min(later_dates) <= max(train_dates):
                raise ValueError('Dates overlap')
        except (TypeError, ValueError) as exc:
            raise ValueError('Later evaluation requires verified non-overlapping ISO publication dates for every activity') from exc
    if not kept:
        raise ValueError('No unseen molecules/fingerprints remain for evaluation')
    labels = np.array([int(row[2] >= THRESHOLD) for row in kept])
    if len(set(labels)) != 2:
        raise ValueError('Evaluation needs both classes after overlap removal')
    probabilities = bundle['model'].predict_proba(np.stack([fingerprint(row[0]) for row in kept]))[:, 1]
    previous = session.scalars(select(ExternalEvaluation).where(ExternalEvaluation.dataset_version_id == version.id)).all()
    known_sources = bool(train_docs and test_docs)
    results = {'mode': mode, 'n_molecules': len(kept), 'overlap_removed': len(examples) - len(kept),
               'conflicting_molecules_excluded': conflicts, 'metrics': classification_metrics(labels, probabilities),
               'training_manifest': training.manifest_sha256, 'evaluation_manifest': version.manifest_sha256,
               'evaluated_smiles': [row[0] for row in kept], 'prior_evaluations_on_dataset': len(previous),
               'independence_established': known_sources and training.source != 'synthetic_fixture',
               'source_history_known': known_sources, 'calibration': 'not_fitted',
               'notice': 'Synthetic results are demonstrations only. Repeated evaluation can inform selection; original experimental independence still requires review.'}
    evaluation = ExternalEvaluation(experiment_id=run.id, dataset_version_id=version.id, results_json=results)
    session.add(evaluation)
    session.commit()
    return {'id': evaluation.id, **results}


def model_card(run, version, external_evaluations=None):
    return {'schema_version': 1, 'external_evaluations': external_evaluations or [], 'experiment_id': run.id, 'dataset_version_id': version.id,
            'status': 'synthetic_demonstration' if run.data_source == 'synthetic_fixture' else 'experimental',
            'target': run.target_id, 'endpoint': version.endpoint_group, 'intended_use': 'Exploratory assay-activity research',
            'model_kind': run.model_kind, 'molecules': run.n_molecules, 'scaffolds': run.n_scaffolds,
            'dataset_manifest': version.manifest_sha256, 'artifact_sha256': run.artifact_sha256,
            'training_provenance': run.provenance_json, 'development_evaluation': run.metrics,
            'calibration_status': 'Uncalibrated; synthetic or insufficient reviewed calibration data',
            'applicability_status': 'Nearest-compound context only; no validated applicability threshold',
            'prohibited_interpretations': ['Drug efficacy', 'Clinical safety', 'Probability of therapeutic success'],
            'release_policy': 'Research-evaluated status requires a separate documented scientific release decision; never inferred from a high metric'}



def evaluation_records(session, experiment_id):
    return [{'id': r.id, 'dataset_version_id': r.dataset_version_id, 'created_at': r.created_at.isoformat(),
             'results': r.results_json} for r in session.scalars(select(ExternalEvaluation).where(
                 ExternalEvaluation.experiment_id == experiment_id).order_by(ExternalEvaluation.id))]
