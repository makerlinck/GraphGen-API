from pathlib import Path

from pydantic_settings import BaseSettings


class Config(BaseSettings):
    HOST: str = "0.0.0.0"
    PORT: int = 8001
    DATASETS_DIR: str = str(Path(__file__).resolve().parents[2] / "datasets")
    CACHE_DIR: str = "cache"
    JOBS_DIR: str = "cache/jobs"
    LOG_DIR: str = "cache/logs"

    model_config = {"env_prefix": "GRAPHGEN_"}


config = Config()
