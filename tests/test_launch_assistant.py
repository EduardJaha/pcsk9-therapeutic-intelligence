"""Mocked runtime startup/ownership checks; no inference or model downloads."""
from unittest.mock import Mock

import pytest

from cvti import assistant, launch
from cvti.config import Settings


@pytest.fixture
def configured(tmp_path):
    store = tmp_path / 'models'
    store.mkdir()
    executable = tmp_path / 'ollama.exe'
    executable.touch()
    return Settings(_env_file=None, assistant_autostart=True,
                    assistant_model='local-pilot:test', assistant_base_url='http://127.0.0.1:11435',
                    assistant_models_dir=str(store), assistant_ollama_executable=str(executable))


def test_disabled_assistant_never_starts_or_queries_runtime(monkeypatch):
    probe = Mock(side_effect=AssertionError('No runtime operations expected'))
    monkeypatch.setattr(assistant, 'model_status', probe)
    monkeypatch.setattr(launch.subprocess, 'Popen', probe)
    children = []
    launch.start_assistant(Settings(_env_file=None), children)
    assert children == []


def test_existing_runtime_is_reused_without_taking_ownership(configured, monkeypatch):
    monkeypatch.setattr(assistant, 'model_status', lambda settings: {'ready': True})
    spawn = Mock(side_effect=AssertionError('Existing service must be reused'))
    monkeypatch.setattr(launch.subprocess, 'Popen', spawn)
    children = []
    launch.start_assistant(configured, children)
    assert children == []


def test_new_runtime_is_local_cloud_disabled_and_owned(configured, monkeypatch):
    monkeypatch.setattr(assistant, 'model_status', Mock(side_effect=[
        {'ready': False, 'status': 'unavailable'}, {'ready': True}]))
    monkeypatch.setattr(launch, 'server_check', lambda *args: {'status': 'stopped'})
    child = Mock()
    child.poll.return_value = None
    spawn = Mock(return_value=child)
    monkeypatch.setattr(launch.subprocess, 'Popen', spawn)
    children = []
    launch.start_assistant(configured, children)
    assert children == [child]
    assert spawn.call_args.args == ([configured.assistant_ollama_executable, 'serve'],)
    env = spawn.call_args.kwargs['env']
    assert env['OLLAMA_HOST'] == 'http://127.0.0.1:11435'
    assert env['OLLAMA_NO_CLOUD'] == '1'
    assert env['OLLAMA_MODELS'] == configured.assistant_models_dir


@pytest.mark.parametrize('state', ['missing_model', 'unsupported_model'])
def test_occupied_service_never_replaced_or_switched(configured, monkeypatch, state):
    monkeypatch.setattr(assistant, 'model_status', lambda settings:
                        {'ready': False, 'status': state, 'message': 'Unavailable selected model'})
    monkeypatch.setattr(launch, 'server_check', lambda *args: {'status': 'running'})
    monkeypatch.setattr(launch.subprocess, 'Popen', Mock(side_effect=AssertionError('No replacement')))
    with pytest.raises(ValueError, match='inspect the local service'):
        launch.start_assistant(configured, [])


def test_missing_store_or_executable_is_actionable(configured, monkeypatch):
    monkeypatch.setattr(assistant, 'model_status', lambda settings: {'ready': False, 'status': 'unavailable'})
    monkeypatch.setattr(launch, 'server_check', lambda *args: {'status': 'stopped'})
    configured.assistant_models_dir += '-missing'
    with pytest.raises(ValueError, match='model store is missing'):
        launch.start_assistant(configured, [])
    configured.assistant_models_dir = configured.assistant_models_dir.removesuffix('-missing')
    configured.assistant_ollama_executable += '-missing'
    with pytest.raises(ValueError, match='executable is missing'):
        launch.start_assistant(configured, [])


def test_startup_failure_cleans_owned_runtime(configured, monkeypatch):
    monkeypatch.setattr('cvti.config.get_settings', lambda: configured)
    monkeypatch.setattr(launch, 'server_check', lambda *args: {'status': 'stopped'})
    monkeypatch.setattr('cvti.db.make_engine', lambda *args: Mock())
    monkeypatch.setattr('cvti.db.prepare_database', lambda *args: None)
    child = Mock()
    child.poll.return_value = None

    def failed_start(settings, children):
        children.append(child)
        raise RuntimeError('Runtime failed before API startup')

    monkeypatch.setattr(launch, 'start_assistant', failed_start)
    with pytest.raises(RuntimeError, match='Runtime failed'):
        launch.start()
    child.terminate.assert_called_once()
    child.wait.assert_called_once()


def test_missing_model_after_runtime_boot_has_no_download(configured, monkeypatch):
    monkeypatch.setattr(assistant, 'model_status', Mock(side_effect=[
        {'ready': False, 'status': 'unavailable'},
        {'ready': False, 'status': 'missing_model', 'message': 'Selected model is missing'}]))
    monkeypatch.setattr(launch, 'server_check', lambda *args: {'status': 'stopped'})
    child = Mock()
    child.poll.return_value = None
    spawn = Mock(return_value=child)
    monkeypatch.setattr(launch.subprocess, 'Popen', spawn)
    with pytest.raises(ValueError, match='No model was downloaded'):
        launch.start_assistant(configured, [])
    assert spawn.call_count == 1
    assert spawn.call_args.args[0][-1] == 'serve'
