import os

from api.config import settings


def setup_workspace():
    os.makedirs(settings.cache_dir, exist_ok=True)
    os.makedirs(settings.jobs_dir, exist_ok=True)
    os.makedirs(settings.log_dir, exist_ok=True)
    os.makedirs(settings.datasets_dir, exist_ok=True)
