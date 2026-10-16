from cvti.config import Settings
from cvti.doctor import diagnose
from cvti.db import init_db, make_engine


def test_doctor_does_not_create_missing_database(tmp_path, monkeypatch):
    monkeypatch.setattr('cvti.doctor.server_check', lambda *args: {'status': 'stopped'})
    path = tmp_path / 'missing' / 'data.db'
    result = diagnose(Settings(database_url=f'sqlite:///{path}', artifact_dir=str(tmp_path / 'models')))
    assert result['database']['status'] == 'error'
    assert not path.parent.exists()


def test_doctor_current_schema_without_models_is_ready(tmp_path, monkeypatch):
    monkeypatch.setattr('cvti.doctor.server_check', lambda *args: {'status': 'stopped'})
    url = f'sqlite:///{tmp_path / "empty.db"}'
    engine = make_engine(url)
    init_db(engine)
    engine.dispose()
    assert diagnose(Settings(database_url=url, artifact_dir=str(tmp_path / 'models')))['ok']
