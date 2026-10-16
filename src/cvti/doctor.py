"""Read-only diagnostics: never migrate a database or create demo records."""
from pathlib import Path
import socket

import httpx
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, select, text
from sqlalchemy.engine import make_url

from cvti.config import get_settings
from cvti.db import make_engine, session_factory
from cvti.models import Experiment
from cvti.training_provenance import verify_artifact


def server_check(host, port, path):
    try:
        with socket.create_connection((host, port), timeout=1):
            pass
    except OSError:
        return {'status': 'stopped', 'message': f'Nothing listening on {host}:{port}'}
    try:
        response = httpx.get(f'http://{host}:{port}{path}', timeout=2, trust_env=False)
        if response.status_code == 200:
            if path == '/health' and response.json().get('scope') != 'research-only':
                raise ValueError('Different API')
            return {'status': 'running', 'message': f'Open http://{host}:{port}'}
    except (httpx.HTTPError, ValueError):
        pass
    return {'status': 'occupied', 'message': f'Port {port} is occupied by an unrecognized or unhealthy service; use another port'}


def diagnose(settings=None, *, api_port=8000, dashboard_port=8501):
    settings = settings or get_settings()
    url = make_url(settings.database_url)
    result = {'database': {'url': url.render_as_string(hide_password=True)},
              'artifacts': {'directory': str(Path(settings.artifact_dir).resolve())}}
    engine = None
    try:
        if url.get_backend_name() == 'sqlite' and (url.database == ':memory:' or not Path(url.database).is_file()):
            raise ValueError('Database does not exist. Run cvti db upgrade')
        engine = make_engine(settings.database_url)
        tables = inspect(engine).get_table_names()
        if 'alembic_version' not in tables:
            raise ValueError('Database schema is not versioned. Run cvti db upgrade after backing up')
        config = Config(str(Path(__file__).parents[2] / 'alembic.ini'))
        head = ScriptDirectory.from_config(config).get_current_head()
        with engine.connect() as conn:
            revision = conn.execute(text('SELECT version_num FROM alembic_version')).scalar_one()
        result['database'].update(status='ok' if revision == head else 'upgrade_needed', revision=revision, expected_revision=head)
        problems = []
        legacy = []
        if revision == head:
            with session_factory(engine)() as session:
                for run in session.scalars(select(Experiment)):
                    try:
                        verify_artifact(run)
                        if not run.artifact_sha256:
                            legacy.append(run.id)
                    except ValueError as exc:
                        problems.append(str(exc))
        result['artifacts'].update(status='error' if problems else 'ok', problems=problems, legacy_unverified_experiments=legacy)
    except ValueError as exc:
        result['database'].update(status='error', message=str(exc))
    except Exception:
        result['database'].update(status='error', message='Unable to inspect database; check configuration and permissions')
    finally:
        if engine is not None:
            engine.dispose()
    result['api'] = server_check('127.0.0.1', api_port, '/health')
    result['dashboard'] = server_check('127.0.0.1', dashboard_port, '/_stcore/health')
    result['ok'] = result['database']['status'] == 'ok' and result['artifacts'].get('status') == 'ok'
    return result
