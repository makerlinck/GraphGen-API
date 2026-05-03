import json
import os
import tempfile
import time

import pytest
from fastapi.testclient import TestClient

import api.config as _config
from api.main import app


@pytest.fixture(autouse=True)
def temp_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        _config.settings.jobs_dir = os.path.join(tmpdir, "jobs")
        _config.settings.cache_dir = tmpdir
        _config.settings.log_dir = os.path.join(tmpdir, "logs")
        _config.settings.datasets_dir = tmpdir  # use temp dir as datasets
        os.makedirs(_config.settings.jobs_dir, exist_ok=True)
        yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def input_file():
    """Create a valid input file in the temp datasets dir and return its name."""
    # Called within temp_dirs context, datasets_dir is already set to tmpdir
    datasets = _config.settings.datasets_dir
    filepath = os.path.join(datasets, "input.jsonl")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write('{"content": "test document about machine learning"}\n')
    return "input.jsonl"


class TestHealthRoute:
    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestConnectionRoutes:
    def test_validate_connection_bad_url(self, client):
        response = client.post(
            "/api/v1/connections/validate",
            json={
                "base_url": "https://invalid.example.com/v1",
                "api_key": "fake",
                "model": "gpt-4",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "message" in data


class TestJobsRoutes:
    def test_create_job(self, client, input_file):
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_file": input_file,
                "api_key": "sk-test",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "pending"

    def test_create_job_missing_required(self, client):
        response = client.post("/api/v1/jobs", json={})
        assert response.status_code == 422

    def test_create_job_nonexistent_input(self, client):
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_file": "nonexistent.jsonl",
                "api_key": "sk",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        assert response.status_code == 422
        assert "not found" in response.json()["detail"]

    def test_create_job_path_traversal_denied(self, client):
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_file": "../../etc/passwd",
                "api_key": "sk",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        assert response.status_code == 422
        assert "path traversal" in response.json()["detail"].lower()

    def test_create_job_invalid_json(self, client):
        datasets = _config.settings.datasets_dir
        path = os.path.join(datasets, "bad.jsonl")
        with open(path, "w") as f:
            f.write("not valid json {{{")
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_file": "bad.jsonl",
                "api_key": "sk",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        assert response.status_code == 422
        assert "invalid JSON" in response.json()["detail"]

    def test_create_job_missing_content_field(self, client):
        datasets = _config.settings.datasets_dir
        path = os.path.join(datasets, "alpaca.jsonl")
        with open(path, "w") as f:
            f.write('{"instruction":"do X","output":"result"}\n')
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_file": "alpaca.jsonl",
                "api_key": "sk",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        assert response.status_code == 422
        detail = response.json()["detail"].lower()
        assert "content" in detail or "missing required field" in detail

    def test_create_job_empty_file(self, client):
        datasets = _config.settings.datasets_dir
        path = os.path.join(datasets, "empty.jsonl")
        open(path, "w").close()
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_file": "empty.jsonl",
                "api_key": "sk",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        assert response.status_code == 422
        assert "empty" in response.json()["detail"].lower()

    def test_get_nonexistent_job(self, client):
        response = client.get("/api/v1/jobs/nonexistent")
        assert response.status_code == 404

    def test_get_job(self, client, input_file):
        gen_resp = client.post(
            "/api/v1/jobs",
            json={
                "input_file": input_file,
                "api_key": "sk-test",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        job_id = gen_resp.json()["job_id"]
        response = client.get(f"/api/v1/jobs/{job_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == job_id
        assert data["status"] in ("pending", "running", "done", "failed")
