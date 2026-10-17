import json

import pytest

from cvti.dashboard_state import WorkspaceStore, workspace_token


def test_workspace_storage_isolated_and_only_restores_allowlisted_state(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKSPACE_STATE_DIR', str(tmp_path))
    store = WorkspaceStore('http://127.0.0.1:8000')
    token = workspace_token(None)
    store.save(token, {'profile_smiles': 'Oc1ccccc1', 'active_project': 2,
                       'scoring_model': None, 'assistant_answer': {'private': 'text'}})
    assert store.load(token) == {'profile_smiles': 'Oc1ccccc1', 'active_project': 2, 'scoring_model': None}
    assert store.load(workspace_token(None)) == {}
    assert WorkspaceStore('http://127.0.0.1:8001').load(token) == {}
    assert not list(tmp_path.rglob('*.tmp'))
    assert workspace_token(token) == token
    assert workspace_token('../../outside') != '../../outside'
    with pytest.raises(ValueError):
        store.load('../../outside')
    with pytest.raises(ValueError):
        store.save('../../outside', {})


@pytest.mark.parametrize('content', ['{', '[]', '{"version":2,"state":{}}'])
def test_invalid_snapshots_fail_safely(tmp_path, monkeypatch, content):
    monkeypatch.setenv('WORKSPACE_STATE_DIR', str(tmp_path))
    store = WorkspaceStore('local-api')
    token = workspace_token(None)
    store.save(token, {})
    path = next(tmp_path.rglob('*.json'))
    path.write_text(content)
    with pytest.raises(ValueError):
        store.load(token)


def test_snapshot_checksum_detects_changed_result(tmp_path, monkeypatch):
    monkeypatch.setenv('WORKSPACE_STATE_DIR', str(tmp_path))
    store = WorkspaceStore('local-api')
    token = workspace_token(None)
    store.save(token, {'profile_smiles': 'Oc1ccccc1'})
    path = next(tmp_path.rglob('*.json'))
    payload = json.loads(path.read_text())
    payload['state']['profile_smiles'] = 'Cc1ccccc1'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        store.load(token)
