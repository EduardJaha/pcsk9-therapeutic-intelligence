from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/cvti.db"
    artifact_dir: str = "./data/artifacts"
    chembl_base_url: str = "https://www.ebi.ac.uk/chembl/api/data"
    open_targets_graphql_url: str = "https://api.platform.opentargets.org/api/v4/graphql"
    http_timeout_seconds: float = 20
    http_max_retries: int = 3
    http_backoff_seconds: float = 1
    chembl_max_records: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
