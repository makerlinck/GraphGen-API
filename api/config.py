from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8001
    datasets_dir: str = "datasets"
    cache_dir: str = "cache"
    jobs_dir: str = "cache/jobs"
    log_dir: str = "cache/logs"

    model_config = {"env_prefix": "GRAPHGEN_"}


settings = Settings()
