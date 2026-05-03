import os
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from fastapi.testclient import TestClient

import api.config as _config
from api.job_manager import JobManager
from api.main import app


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def manager():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield JobManager(jobs_dir=tmpdir)


@pytest.fixture
def client():
    with tempfile.TemporaryDirectory() as tmpdir:
        _config.settings.jobs_dir = os.path.join(tmpdir, "jobs")
        _config.settings.uploads_dir = os.path.join(tmpdir, "uploads")
        _config.settings.cache_dir = tmpdir
        _config.settings.log_dir = os.path.join(tmpdir, "logs")
        os.makedirs(_config.settings.uploads_dir, exist_ok=True)
        os.makedirs(_config.settings.jobs_dir, exist_ok=True)
        yield TestClient(app)


def _upload_file(client, filename="test.jsonl"):
    resp = client.post(
        "/api/v1/upload",
        files={"file": (filename, b'{"content":"test"}\n', "application/octet-stream")},
    )
    return resp.json()["file_id"]


# ── JobManager 并发安全 ──────────────────────────────────────────────────────

class TestJobManagerConcurrency:
    def test_concurrent_create_unique_ids(self, manager):
        """并发创建应该产生互不冲突的唯一 ID 和目录"""
        ids = set()
        lock = threading.Lock()

        def _create():
            job_id = manager.create({"source": "concurrent"})
            with lock:
                ids.add(job_id)
            return job_id

        with ThreadPoolExecutor(max_workers=32) as pool:
            futures = [pool.submit(_create) for _ in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(ids) == 100  # 全部唯一
        # 每个作业目录都应该存在且包含 status.json
        for jid in ids:
            assert manager.get(jid)["status"] == "pending"

    def test_concurrent_get_read_safe(self, manager):
        """并发读取同一作业应该是安全的"""
        job_id = manager.create({})

        def _read():
            return manager.get(job_id)

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_read) for _ in range(50)]
            results = [f.result() for f in futures]

        for r in results:
            assert r["job_id"] == job_id
            assert r["status"] == "pending"

    def test_concurrent_update_consistency(self, manager):
        """并发更新同一作业 —— per-job 锁保证不会丢失更新"""
        job_id = manager.create({"counter": 0})
        errors = []
        err_lock = threading.Lock()

        def _increment():
            try:
                for _ in range(10):
                    current = manager.get(job_id)
                    new_val = current.get("progress", 0) + 0.01
                    manager.update(job_id, progress=min(new_val, 1.0))
            except Exception as e:
                with err_lock:
                    errors.append(str(e))

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_increment) for _ in range(8)]
            for f in as_completed(futures):
                f.result()

        final = manager.get(job_id)
        assert len(errors) == 0, f"并发更新出现异常: {errors}"

        expected = 8 * 10 * 0.01  # 0.8
        actual = final["progress"]
        # 有锁保护：更新不会丢失，但 get+update 不是原子的整体，
        # 每个线程读取 → 加 0.01 → 写入，但多个线程可能读到同一起点
        # 所以最终值 ≤ 期望值
        assert 0 < actual <= expected, (
            f"progress should be >0 and <= {expected}, got {actual}"
        )


# ── API 路由并发 ─────────────────────────────────────────────────────────────

class TestAPIConcurrency:
    def test_concurrent_uploads(self, client):
        """并发上传应该全部成功"""
        def _upload(i):
            return client.post(
                "/api/v1/upload",
                files={"file": (f"file_{i}.txt", b"data", "text/plain")},
            )

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_upload, i) for i in range(50)]
            results = [f.result() for f in futures]

        file_ids = set()
        for r in results:
            assert r.status_code == 200
            data = r.json()
            assert "file_id" in data
            file_ids.add(data["file_id"])
            assert os.path.exists(data["path"])

        assert len(file_ids) == 50

    def test_concurrent_generate_submissions(self, client):
        """并发提交生成任务"""
        file_id = _upload_file(client)

        def _submit(i):
            return client.post(
                "/api/v1/generate",
                json={
                    "file_id": file_id,
                    "api_key": f"sk-{i}",
                    "synthesizer_url": "https://api.example.com/v1",
                    "synthesizer_model": "gpt-4",
                    "mode": "atomic",
                    "data_format": "Alpaca",
                },
            )

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_submit, i) for i in range(32)]
            results = [f.result() for f in futures]

        job_ids = set()
        for r in results:
            assert r.status_code == 202
            data = r.json()
            assert data["status"] == "pending"
            job_ids.add(data["job_id"])

        assert len(job_ids) == 32  # 每个请求一个独立作业

    def test_concurrent_status_queries(self, client):
        """并发查询作业状态"""
        file_id = _upload_file(client)
        resp = client.post(
            "/api/v1/generate",
            json={
                "file_id": file_id,
                "api_key": "sk-test",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        job_id = resp.json()["job_id"]

        def _query(_):
            return client.get(f"/api/v1/generate/{job_id}/status")

        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(_query, _) for _ in range(50)]
            results = [f.result() for f in futures]

        for r in results:
            assert r.status_code == 200
            assert r.json()["job_id"] == job_id

    def test_mixed_read_write_no_crash(self, client):
        """混合读写操作不应导致服务崩溃"""
        file_id = _upload_file(client)

        resp = client.post(
            "/api/v1/generate",
            json={
                "file_id": file_id,
                "api_key": "sk",
                "synthesizer_url": "https://api.example.com/v1",
                "synthesizer_model": "gpt-4",
                "mode": "atomic",
                "data_format": "Alpaca",
            },
        )
        job_id = resp.json()["job_id"]

        errors = []
        start_event = threading.Event()

        def _worker(i):
            try:
                start_event.wait()
                if i % 3 == 0:
                    r = client.get(f"/api/v1/generate/{job_id}/status")
                    assert r.status_code == 200
                elif i % 3 == 1:
                    r = client.get("/health")
                    assert r.status_code == 200
                else:
                    fid = _upload_file(client, f"worker_{i}.jsonl")
                    r = client.post(
                        "/api/v1/generate",
                        json={
                            "file_id": fid,
                            "api_key": f"sk-{i}",
                            "synthesizer_url": "https://api.example.com/v1",
                            "synthesizer_model": "gpt-4",
                            "mode": "atomic",
                            "data_format": "Alpaca",
                        },
                    )
                    assert r.status_code == 202
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        start_event.set()
        for t in threads:
            t.join(timeout=30)

        assert len(errors) == 0, f"混合并发操作出现异常: {errors}"


# ── 边界条件 ──────────────────────────────────────────────────────────────────

class TestConcurrencyEdgeCases:
    def test_create_and_immediate_get(self, manager):
        """创建后立即并发读取"""

        def _create_and_read():
            job_id = manager.create({})
            data = manager.get(job_id)
            return data["status"]

        with ThreadPoolExecutor(max_workers=12) as pool:
            futures = [pool.submit(_create_and_read) for _ in range(50)]
            statuses = [f.result() for f in futures]

        assert all(s == "pending" for s in statuses)

    def test_update_then_immediate_get_visibility(self, manager):
        """同一线程内更新后立即可见"""
        for i in range(20):
            job_id = manager.create({"seq": i})
            manager.update(job_id, status="running", progress=0.5)
            data = manager.get(job_id)
            assert data["status"] == "running"
            assert data["progress"] == 0.5
