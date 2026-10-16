"""Exercise the real CLI/services/recovery in a disposable workspace, never user data.

Run from the repository: python scripts/release_smoke.py
"""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

import httpx


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def main():
    with tempfile.TemporaryDirectory(prefix='cvti-release-') as folder:
        root = Path(folder)
        env = {**os.environ, 'DATABASE_URL': f'sqlite:///{root / "source" / "database.db"}',
               'ARTIFACT_DIR': str(root / 'source' / 'models')}
        def cli(*args, configuration=None):
            process = subprocess.run([sys.executable, '-m', 'cvti.cli', *args], env=configuration or env,
                                     capture_output=True, text=True, timeout=60)
            if process.returncode:
                raise RuntimeError(f'CLI {args[0]} failed: {process.stderr}')
            return json.loads(process.stdout)
        cli('db', 'upgrade')
        assert cli('ingest', '--source', 'fixture')['inserted_measurements'] == 24
        run = cli('train')
        prediction = cli('predict', 'CC1CCCCC1')
        api_port, dashboard_port = free_port(), free_port()
        while api_port == dashboard_port:
            dashboard_port = free_port()
        with (root / 'services.log').open('w') as log:
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
            process = subprocess.Popen([sys.executable, '-m', 'cvti.cli', 'start', '--api-port', str(api_port),
                                        '--dashboard-port', str(dashboard_port)], env=env, stdout=log, stderr=log,
                                       creationflags=flags)
            try:
                with httpx.Client(base_url=f'http://127.0.0.1:{api_port}', timeout=5, trust_env=False) as client:
                    deadline = time.monotonic() + 40
                    while time.monotonic() < deadline:
                        if process.poll() is not None:
                            raise RuntimeError('Launcher stopped: ' + (root / 'services.log').read_text())
                        try:
                            api = client.get('/health')
                            dashboard = httpx.get(f'http://127.0.0.1:{dashboard_port}/_stcore/health', timeout=2, trust_env=False)
                            if api.status_code == dashboard.status_code == 200:
                                break
                        except httpx.HTTPError:
                            pass
                        time.sleep(0.2)
                    else:
                        raise RuntimeError('Services did not become healthy')
                    response = client.post('/batch-jobs', json={'csv_content': 'smiles\nOc1ccccc1\nc1ccccc1O\ninvalid\nCc1ccccc1',
                                                               'smiles_column': 'smiles', 'experiment_id': run['experiment_id'],
                                                               'save_predictions': True})
                    response.raise_for_status()
                    identifier = response.json()['id']
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        job = client.get(f'/batch-jobs/{identifier}').json()
                        if job['status'] == 'completed':
                            break
                        time.sleep(0.2)
                    else:
                        raise RuntimeError('Worker did not finish the batch')
                    assert [row['status'] for row in job['results']] == ['ok', 'duplicate', 'error', 'ok']
                    assert client.get('/summary').json()['predictions'] == 3
                    assert client.get(f'/research-reports/{run["experiment_id"]}?prediction_ids=1').status_code == 200
            finally:
                if os.name == 'nt':
                    process.send_signal(signal.CTRL_BREAK_EVENT)
                else:
                    process.terminate()
                process.wait(timeout=25)
        archive = root / 'backup.zip'
        cli('backup', 'create', '--output', str(archive), '--services-stopped')
        manifest = cli('backup', 'verify', str(archive))
        recovered = root / 'recovered'
        cli('backup', 'restore', str(archive), '--destination', str(recovered), '--services-stopped')
        restored_env = {**env, 'DATABASE_URL': f'sqlite:///{recovered / "database.sqlite"}',
                        'ARTIFACT_DIR': str(recovered / 'artifacts')}
        result = cli('predict', 'CC1CCCCC1', configuration=restored_env)
        assert result['probability_exploratory_activity'] == prediction['probability_exploratory_activity']
        assert result['manifest_sha256'] == prediction['manifest_sha256']
        assert cli('doctor', configuration=restored_env)['ok']
        print(json.dumps({'status': 'passed', 'exercise': 'CLI + API + dashboard + worker + relocated restore',
                          'schema_revision': manifest['schema_revision'], 'model_checksum_verified': result['artifact_integrity']}, indent=2))


if __name__ == '__main__':
    main()
