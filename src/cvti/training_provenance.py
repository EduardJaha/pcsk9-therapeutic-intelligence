"""Capture the training environment without credentials or user filesystem paths."""
import hashlib
import importlib.metadata
from pathlib import Path
import platform
import subprocess


def file_sha256(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def capture_provenance():
    root = Path(__file__).resolve().parents[2]
    def git(*args):
        try:
            result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True, timeout=5)
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    revision = git('rev-parse', 'HEAD')
    status = git('status', '--porcelain')
    distributions = {d.metadata['Name']: d.version for d in importlib.metadata.distributions() if d.metadata['Name']}
    lock = root / 'uv.lock'
    return {'schema_version': 1, 'git_revision': revision, 'git_dirty': bool(status) if status is not None else None,
            'python_version': platform.python_version(), 'platform': platform.system(),
            'dependencies': dict(sorted(distributions.items())),
            'lockfile_sha256': file_sha256(lock) if lock.is_file() else None,
            'fingerprint': {'kind': 'Morgan', 'radius': 2, 'bits': 2048, 'include_chirality': False},
            'standardization': 'RDKit ChargeParent then canonical isomeric SMILES; ring scaffold required',
            'model_parameters': {'n_estimators': 150, 'class_weight': 'balanced', 'random_state': 42, 'n_jobs': 1},
            'evaluation_seed': 42, 'activity_threshold_pchembl': 6.0, 'classification_threshold': 0.5}


def verify_artifact(run):
    path = Path(run.artifact_path)
    if not path.is_file():
        raise ValueError(f'Model artifact missing for experiment {run.id}; restore the workspace backup')
    if run.artifact_sha256 and file_sha256(path) != run.artifact_sha256:
        raise ValueError(f'Model artifact checksum failed for experiment {run.id}; no model was loaded')
    return path
