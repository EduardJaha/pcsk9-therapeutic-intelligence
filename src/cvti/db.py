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

    config_path = Path(__file__).resolve().parents[2] / "alembic.ini"
    if not config_path.is_file():
        config_path = Path.cwd() / "alembic.ini"
    if not config_path.is_file():
        raise RuntimeError("alembic.ini is missing; run from the project directory")
    config = Config(str(config_path))
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
                    return change[1].name == "dataset_versions"
                if change[0] == "add_column":
                    return change[2] == "experiments" and change[3].name == "dataset_version_id"
                if change[0] == "add_fk":
                    fk = change[1]
                    return (fk.table.name == "experiments"
                            and list(fk.columns.keys()) == ["dataset_version_id"])
                return False

            baseline_tables = set(Base.metadata.tables) - {"dataset_versions"}
            if existing_tables != baseline_tables or not all(expected_addition(change) for change in differences):
                raise RuntimeError("Existing database schema differs from the MVP baseline; back up and review it before migration")
            command.stamp(config, "2cf3a3fb0c41")
        command.upgrade(config, "head")
