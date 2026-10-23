from functools import lru_cache
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.exc import ArgumentError
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/cvti.db"
    artifact_dir: str = "./data/artifacts"
    workspace_state_dir: str = "./data/workspaces"
    chembl_base_url: str = "https://www.ebi.ac.uk/chembl/api/data"
    open_targets_graphql_url: str = "https://api.platform.opentargets.org/api/v4/graphql"
    http_timeout_seconds: float = Field(default=20, gt=0)
    http_max_retries: int = Field(default=3, ge=0, le=10)
    http_backoff_seconds: float = Field(default=1, ge=0)
    chembl_max_records: int = Field(default=500, ge=1, le=5000)
    batch_max_rows: int = Field(default=1000, ge=1, le=10000)
    assistant_base_url: str = "http://127.0.0.1:11434"
    assistant_model: str = ""
    discovery_python: str = './data/runtime/discovery/bin/python'
    admet_manifest: str = './data/models/admet-manifest.json'
    vina_executable: str = './data/runtime/vina'
    discovery_timeout_seconds: int = Field(default=600, ge=10, le=3600)
    assistant_timeout_seconds: float = Field(default=45, gt=0, le=50)

    @field_validator("assistant_base_url")
    @classmethod
    def validate_assistant_url(cls, value: str) -> str:
        parts = urlsplit(value)
        if (parts.scheme != 'http' or parts.hostname not in {'localhost', '127.0.0.1', '::1'}
                or parts.username or parts.password or parts.path not in {'', '/'}
                or parts.query or parts.fragment):
            raise ValueError('ASSISTANT_BASE_URL must be a local loopback HTTP address')
        try:
            parts.port
        except ValueError as exc:
            raise ValueError('Invalid assistant port') from exc
        return value.rstrip('/')

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        try:
            backend = make_url(value).get_backend_name()
        except ArgumentError as exc:
            raise ValueError("DATABASE_URL is not a valid SQLAlchemy URL") from exc
        if backend not in {"sqlite", "postgresql"}:
            raise ValueError("DATABASE_URL must use SQLite or PostgreSQL")
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
