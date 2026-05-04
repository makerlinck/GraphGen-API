import os

from api.config import config


def setup_workspace():
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.JOBS_DIR, exist_ok=True)
    os.makedirs(config.LOG_DIR, exist_ok=True)
    os.makedirs(config.DATASETS_DIR, exist_ok=True)
