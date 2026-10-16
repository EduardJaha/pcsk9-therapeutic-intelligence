"""One foreground command owns both local servers; Ctrl+C stops its children."""
import os
import signal
import subprocess
import sys
import time

from cvti.doctor import server_check


def start(api_port=8000, dashboard_port=8501):
    for port, path in [(api_port, '/health'), (dashboard_port, '/_stcore/health')]:
        check = server_check('127.0.0.1', port, path)
        if check['status'] != 'stopped':
            raise ValueError(check['message'] + '; stop existing services before cvti start')
    children = []
    env = dict(os.environ, API_URL=f'http://127.0.0.1:{api_port}', API_REFERENCE_URL=f'http://127.0.0.1:{api_port}/docs')
    commands = [[sys.executable, '-m', 'uvicorn', 'cvti.api:app', '--host', '127.0.0.1', '--port', str(api_port)],
                [sys.executable, '-m', 'streamlit', 'run', 'dashboard.py', '--server.address', '127.0.0.1',
                 '--server.port', str(dashboard_port), '--server.headless', 'true']]
    def stop(signum, frame):
        raise KeyboardInterrupt
    previous = signal.signal(signal.SIGTERM, stop)
    try:
        for command in commands:
            children.append(subprocess.Popen(command, env=env))
        print(f'Dashboard: http://127.0.0.1:{dashboard_port} — Ctrl+C stops both services', flush=True)
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
