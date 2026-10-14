"""Alembic environment for SQLite and PostgreSQL."""

from alembic import context
from sqlalchemy import create_engine, pool

from cvti.config import get_settings
from cvti.db import Base
import cvti.models  # noqa: F401 - registers the tables on Base.metadata


config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    return config.attributes.get("database_url") or get_settings().database_url


def configure(connection=None) -> None:
    options = {"target_metadata": target_metadata, "compare_type": True,
               "render_as_batch": database_url().startswith("sqlite:")}
    if connection is None:
        context.configure(url=database_url(), literal_binds=True, dialect_opts={"paramstyle": "named"}, **options)
    else:
        context.configure(connection=connection, **options)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    configure()
else:
    connection = config.attributes.get("connection")
    if connection is not None:
        configure(connection)
    else:
        engine = create_engine(database_url(), poolclass=pool.NullPool)
        with engine.connect() as connection:
            configure(connection)
        engine.dispose()
