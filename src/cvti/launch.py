"""One foreground command owns the app and optional local assistant runtime."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

from cvti.doctor import server_check


def start_assistant(settings, children):
    """Start an explicitly configured local store, or reuse its healthy runtime.

    Append only processes we own so shutdown cannot stop an existing service.
    Never download a missing model or fall back to another model/provider.
    """
    if not settings.assistant_autostart:
        return
    from cvti.assistant import model_status
    if not settings.assistant_model.strip():
        raise ValueError('ASSISTANT_AUTOSTART requires ASSISTANT_MODEL')
    status = model_status(settings)
    if status['ready']:
        print(f"Research assistant: {settings.assistant_model} at {settings.assistant_base_url} (existing local runtime)", flush=True)
        return
    address = urlsplit(settings.assistant_base_url)
    port = address.port or 80
    check = server_check(address.hostname, port, '/api/tags')
    if check['status'] != 'stopped':
        raise ValueError(status['message'] + '; inspect the local service and selected model before restarting')
    store = Path(settings.assistant_models_dir).resolve()
    if not store.is_dir():
        raise ValueError(f'Local assistant model store is missing: {store}. Configure ASSISTANT_MODELS_DIR; no model was downloaded')
    bundled = Path('data/ollama/runtime') / ('ollama.exe' if os.name == 'nt' else 'ollama')
    executable = settings.assistant_ollama_executable or (str(bundled.resolve()) if bundled.is_file() else shutil.which('ollama'))
    if not executable or not Path(executable).is_file():
        raise ValueError('Ollama executable is missing. Install Ollama locally or set ASSISTANT_OLLAMA_EXECUTABLE')
    env = dict(os.environ, OLLAMA_HOST=settings.assistant_base_url, OLLAMA_NO_CLOUD='1', OLLAMA_MODELS=str(store))
    child = subprocess.Popen([executable, 'serve'], env=env)
    children.append(child)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('Local assistant runtime exited; inspect its terminal output')
        status = model_status(settings)
        if status['ready']:
            print(f"Research assistant: {settings.assistant_model} at {settings.assistant_base_url} (local inference)", flush=True)
            return
        if status['status'] in {'missing_model', 'unsupported_model'}:
            raise ValueError(status['message'] + f'; selected local store: {store}. No model was downloaded')
        time.sleep(0.25)
    raise RuntimeError('Local assistant runtime did not become ready within 30 seconds; inspect its terminal output')


def start(api_port=8000, dashboard_port=8501):
    for port, path in [(api_port, '/health'), (dashboard_port, '/_stcore/health')]:
        check = server_check('127.0.0.1', port, path)
        if check['status'] != 'stopped':
            raise ValueError(check['message'] + '; stop existing services before cvti start')
    from cvti.config import get_settings
    from cvti.db import make_engine, prepare_database
    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        prepare_database(engine, settings.database_url, settings.artifact_dir)
    finally:
        engine.dispose()
    children = []
    env = dict(os.environ, API_URL=f'http://127.0.0.1:{api_port}', API_REFERENCE_URL=f'http://127.0.0.1:{api_port}/docs')
    commands = [[sys.executable, '-m', 'cvti.cli', 'worker'],
                [sys.executable, '-m', 'uvicorn', 'cvti.api:app', '--host', '127.0.0.1', '--port', str(api_port)],
                [sys.executable, '-m', 'streamlit', 'run', 'dashboard.py', '--server.address', '127.0.0.1',
                 '--server.port', str(dashboard_port), '--server.headless', 'true']]
    def stop(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, stop)
    previous_break = signal.signal(signal.SIGBREAK, stop) if hasattr(signal, "SIGBREAK") else None
    try:
        start_assistant(settings, children)
        for command in commands:
            children.append(subprocess.Popen(command, env=env))
        print(f'Dashboard: http://127.0.0.1:{dashboard_port} — Ctrl+C stops services started by this command', flush=True)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        if any(child.returncode not in (None, 0) for child in children):
            raise RuntimeError('A server exited; inspect its terminal output')
    except KeyboardInterrupt:
        pass
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        signal.signal(signal.SIGTERM, previous)
        if previous_break is not None:
            signal.signal(signal.SIGBREAK, previous_break)
