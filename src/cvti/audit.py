"""Read-only dataset audit. Software feasibility is not scientific approval."""
from collections import Counter, defaultdict
import hashlib
import json
from types import SimpleNamespace

import numpy as np
from rdkit import Chem

from cvti.chemistry import fingerprint
from cvti.provenance import verify_version


def audit_dataset(version):
    from cvti.ml import THRESHOLD, _examples, _evaluation_splits, _class_counts
    verify_version(version)
    rows = version.records_json
    by_structure = defaultdict(list)
    by_fingerprint = defaultdict(set)
    unknown_stereo = []
    for row in rows:
        smiles = row['canonical_smiles']
        by_structure[smiles].append(row)
        by_fingerprint[hashlib.sha256(fingerprint(smiles).tobytes()).hexdigest()].add(smiles)
        mol = Chem.MolFromSmiles(smiles)
        if any(info.specified == Chem.StereoSpecified.Unspecified for info in Chem.FindPotentialStereo(mol)):
            unknown_stereo.append(smiles)
    examples, conflicts = _examples([SimpleNamespace(**row) for row in rows])
    labels = np.array([int(row[2] >= THRESHOLD) for row in examples])
    groups = np.array([row[1] for row in examples])
    reasons = []
    partitions = None
    if version.status != 'ready':
        reasons.append(f'Dataset status is {version.status}')
    if len(examples) < 12 or len(set(groups)) < 5:
        reasons.append('Need at least 12 distinct molecules across 5 ring scaffolds (software minimum only)')
    if len(set(labels)) != 2:
        reasons.append('Both activity classes are required')
    if not reasons:
        try:
            _, partitions = _evaluation_splits(np.zeros((len(labels), 1)), labels, groups)
        except ValueError as exc:
            reasons.append(str(exc))
    raw = json.loads(version.snapshot_blob) if version.snapshot_blob else {}
    documents = defaultdict(set)
    for row in raw.get('activities', []):
        doc = row.get('document_chembl_id')
        if doc:
            documents[doc].add(row.get('assay_chembl_id'))
    collisions = [sorted(smiles) for smiles in by_fingerprint.values() if len(smiles) > 1]
    duplicates = [{"canonical_smiles": smiles, 'measurements': len(records),
                   'conflicting_labels': min(r['pchembl_value'] for r in records) < THRESHOLD <= max(r['pchembl_value'] for r in records)}
                  for smiles, records in sorted(by_structure.items()) if len(records) > 1]
    return {'schema_version': 1, 'dataset_version_id': version.id, 'manifest_sha256': version.manifest_sha256,
            'source': version.source, 'status': version.status, 'source_release': raw.get('source_release'),
            'snapshot_completeness': raw.get('completeness', 'legacy_unknown'),
            'counts': {'raw_activities': len(raw.get('activities', raw.get('records', []))),
                       'retained_measurements': len(rows), 'distinct_structures_before_aggregation': len(by_structure),
                       'molecules_after_aggregation': len(examples), 'scaffolds': len(set(groups)),
                       'classes_before_aggregation': dict(Counter('active' if r['pchembl_value'] >= THRESHOLD else 'inactive' for r in rows)),
                       'classes_after_aggregation': _class_counts(labels), 'conflicting_molecules_excluded': conflicts},
            'activity_exclusions': version.stats_json.get('excluded_by_reason', {}),
            'duplicate_structures': duplicates, 'identical_fingerprint_groups': collisions,
            'unspecified_stereochemistry': sorted(set(unknown_stereo)),
            'documents_with_multiple_assays': {k: sorted(a for a in v if a) for k, v in documents.items() if len(v) > 1},
            'software_trainable': not reasons, 'blocking_reasons': reasons, 'split_selection': partitions,
            'notice': 'Software feasibility is not independent scientific approval or evidence of predictive usefulness. Published-source overlap requires review.'}
