from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from cvti.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    url = url or get_settings().database_url
    if url.startswith("sqlite:///") and not url.startswith("sqlite:///:memory:"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite:") else {}, pool_pre_ping=True)


def session_factory(engine=None):
    return sessionmaker(bind=engine or make_engine(), expire_on_commit=False)


def init_db(engine):
    import cvti.models  # noqa: F401

    config = migration_config()
    config.attributes["database_url"] = str(engine.url)
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        existing_tables = set(inspect(connection).get_table_names())
        if existing_tables and "alembic_version" not in existing_tables:
            # Preserve databases created by the first MVP. Stamp the baseline only
            # when all differences are additions made by our later migrations.
            differences = compare_metadata(
                MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata
            )
            expected_indexes = {index.name for table in Base.metadata.tables.values() for index in table.indexes}
            def expected_addition(change):
                if change[0] == "add_index":
                    return change[1].name in expected_indexes
                if change[0] == "add_table":
                    return change[1].name in {
                        "dataset_versions", "evaluation_protocols", "external_evaluations", "projects",
                        "collections", "collection_molecules", "batch_jobs", "registered_compounds",
                        "compound_batches", "material_samples", "assay_protocols", "assay_runs",
                        "assay_observations", "registration_imports", "research_views",
                        "discovery_models", "discovery_runs",
                        "literature_records",
                    }
                if change[0] == "add_column":
                    return change[2] in {"experiments", "predictions"} and change[3].name in {"dataset_version_id", "provenance_json", "artifact_sha256", "protocol_id", "project_id"}
                if change[0] == "add_fk":
                    fk = change[1]
                    return (fk.table.name in {"experiments", "predictions"}
                            and list(fk.columns.keys()) in (["dataset_version_id"], ["protocol_id"], ["project_id"]))
                return False

            baseline_tables = {"measurements", "target_evidence", "experiments", "predictions"}
            if existing_tables != baseline_tables or not all(expected_addition(change) for change in differences):
                raise RuntimeError("Existing database schema differs from the MVP baseline; back up and review it before migration")
            command.stamp(config, "2cf3a3fb0c41")
        command.upgrade(config, "head")


def prepare_database(engine, database_url, artifact_dir):
    """Upgrade only under exclusive maintenance lock; current schemas need no write lock."""
    from sqlalchemy import text
    from alembic.script import ScriptDirectory
    from cvti.workspace_lock import workspace_lock
    config = migration_config()
    head = ScriptDirectory.from_config(config).get_current_head()
    try:
        with engine.connect() as connection:
            current = connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one_or_none()
    except Exception:
        current = None
    if current != head:
        with workspace_lock(database_url, artifact_dir):
            init_db(engine)



def migration_config():
    path = Path(__file__).resolve().parents[2] / 'alembic.ini'
    if not path.is_file():
        path = Path.cwd() / 'alembic.ini'
    if not path.is_file():
        raise RuntimeError('alembic.ini is missing; run from the project directory')
    return Config(str(path))
