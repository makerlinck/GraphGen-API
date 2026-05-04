import json
import os
import threading
import uuid
from datetime import datetime, timezone
from typing import Optional


class JobManager:
    def __init__(self, jobs_dir: str = "cache/jobs"):
        self.jobs_dir = jobs_dir
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()
        os.makedirs(jobs_dir, exist_ok=True)

    def _get_lock(self, job_id: str) -> threading.Lock:
        with self._locks_lock:
            if job_id not in self._locks:
                self._locks[job_id] = threading.Lock()
            return self._locks[job_id]

    def create(self, config: dict) -> str:
        job_id = str(uuid.uuid4())
        job_dir = os.path.join(self.jobs_dir, job_id)
        os.makedirs(job_dir, exist_ok=True)
        status = {
            "job_id": job_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
            "progress": 0.0,
            "error": None,
            "output_path": None,
        }
        self._write_status(job_dir, status)
        return job_id

    def get(self, job_id: str) -> dict:
        job_dir = os.path.join(self.jobs_dir, job_id)
        if not os.path.exists(job_dir):
            raise FileNotFoundError(f"Job {job_id} not found")
        with self._get_lock(job_id):
            return self._read_status(job_dir)

    def update_if(self, job_id: str, condition: dict, updates: dict) -> bool:
        """Atomically apply updates only if current state matches condition.

        Returns True if update was applied, False if condition not met.
        """
        job_dir = os.path.join(self.jobs_dir, job_id)
        with self._get_lock(job_id):
            current = self._read_status(job_dir)
            for key, expected in condition.items():
                if current.get(key) != expected:
                    return False
            current.update(updates)
            self._write_status(job_dir, current)
            return True

    def update(self, job_id: str, **kwargs):
        job_dir = os.path.join(self.jobs_dir, job_id)
        with self._get_lock(job_id):
            current = self._read_status(job_dir)
            current.update(kwargs)
            self._write_status(job_dir, current)

    def get_output_dir(self, job_id: str) -> str:
        job_dir = os.path.join(self.jobs_dir, job_id)
        output_dir = os.path.join(job_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        return output_dir

    def get_output_file(self, job_id: str) -> Optional[str]:
        output_dir = self.get_output_dir(job_id)
        generate_dir = os.path.join(output_dir, "generate")
        if not os.path.exists(generate_dir):
            return None
        for f in os.listdir(generate_dir):
            if f.endswith(".jsonl"):
                return os.path.join(generate_dir, f)
        return None

    def _read_status(self, job_dir: str) -> dict:
        status_path = os.path.join(job_dir, "status.json")
        with open(status_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # backward compat: rename legacy field
        if "output_url" in data and "output_path" not in data:
            data["output_path"] = data.pop("output_url")
        data.pop("output_url", None)
        return data

    def _write_status(self, job_dir: str, status: dict):
        status_path = os.path.join(job_dir, "status.json")
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=2)
