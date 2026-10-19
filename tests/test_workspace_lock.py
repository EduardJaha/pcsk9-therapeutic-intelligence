"""Exercise OS locks across processes, including native Windows shared locks."""
import subprocess
import sys

import pytest

from cvti.workspace_lock import lock_path, workspace_lock


PROBE = """
import sys
from cvti.workspace_lock import workspace_lock
try:
    with workspace_lock(sys.argv[1], sys.argv[2], shared=sys.argv[3] == 'True', name=sys.argv[4]):
        print('acquired')
except RuntimeError:
    print('busy')
"""


def probe(url, artifacts, *, shared=False, name='.cvti-workspace.lock'):
    result = subprocess.run(
        [sys.executable, '-c', PROBE, url, str(artifacts), str(shared), name],
        capture_output=True, text=True, timeout=20, check=True,
    )
    return result.stdout.strip()


@pytest.mark.parametrize('holder_shared, contender_shared, expected', [
    (True, True, 'acquired'),
    (True, False, 'busy'),
    (False, True, 'busy'),
    (False, False, 'busy'),
])
def test_lock_compatibility_across_processes(tmp_path, holder_shared, contender_shared, expected):
    url = f'sqlite:///{tmp_path / "workspace.db"}'
    artifacts = tmp_path / 'artifacts'
    with workspace_lock(url, artifacts, shared=holder_shared):
        assert probe(url, artifacts, shared=contender_shared) == expected
    assert probe(url, artifacts) == 'acquired'


def test_releases_after_body_error_and_reuses_existing_lock_file(tmp_path):
    url = f'sqlite:///{tmp_path / "workspace.db"}'
    artifacts = tmp_path / 'artifacts'
    # Accept files created by the previous implementation without deleting them.
    lock_path(url, artifacts).write_bytes(b'0')
    with pytest.raises(ValueError, match='body error'):
        with workspace_lock(url, artifacts, shared=True):
            raise ValueError('body error')
    assert probe(url, artifacts) == 'acquired'


def test_single_worker_lock_is_separate_from_shared_workspace_lock(tmp_path):
    url = f'sqlite:///{tmp_path / "workspace.db"}'
    artifacts = tmp_path / 'artifacts'
    with workspace_lock(url, artifacts, shared=True):
        with workspace_lock(url, artifacts, name='.cvti-worker.lock'):
            assert probe(url, artifacts, shared=True) == 'acquired'
            assert probe(url, artifacts, name='.cvti-worker.lock') == 'busy'
            assert probe(url, artifacts) == 'busy'
    assert probe(url, artifacts, name='.cvti-worker.lock') == 'acquired'
