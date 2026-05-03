import os
import tempfile

import pytest
from pydantic import ValidationError
from api.schemas.connection import TestConnectionRequest, TestConnectionResponse
from api.schemas.generation import GenerateRequest, GenerateResponse, JobStatus


class TestConnectionSchemas:
    def test_request_valid(self):
        req = TestConnectionRequest(
            base_url="https://api.example.com/v1",
            api_key="sk-123",
            model="gpt-4",
        )
        assert req.base_url == "https://api.example.com/v1"

    def test_request_missing_required(self):
        with pytest.raises(ValidationError):
            TestConnectionRequest(base_url="https://api.example.com/v1")

    def test_response_success(self):
        resp = TestConnectionResponse(success=True, message="OK")
        assert resp.success is True

    def test_response_failure(self):
        resp = TestConnectionResponse(success=False, message="Connection refused")
        assert resp.success is False

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            TestConnectionRequest(
                base_url="https://api.example.com/v1",
                api_key="sk-123",
                model="gpt-4",
                unknown_field="should_reject",
            )


class TestGenerationSchemas:
    def test_minimal_request(self):
        req = GenerateRequest(
            input_file="test.jsonl",
            api_key="sk-xxx",
            synthesizer_url="https://api.example.com/v1",
            synthesizer_model="gpt-4",
            mode="atomic",
            data_format="Alpaca",
        )
        assert req.chunk_size == 1024
        assert req.partition_method == "ece"
        assert req.input_file == "test.jsonl"

    def test_full_request(self):
        req = GenerateRequest(
            input_file="input.jsonl",
            api_key="sk",
            synthesizer_url="https://api.example.com/v1",
            synthesizer_model="gpt-4",
            mode="aggregated",
            data_format="Sharegpt",
            tokenizer="gpt2",
            trainee_model="Qwen/Qwen2.5-7B-Instruct",
            trainee_url="https://api.siliconflow.cn/v1",
            trainee_api_key="sk-trainee",
            chunk_size=2048,
            chunk_overlap=200,
            partition_method="leiden",
            leiden_max_size=30,
            rpm=500,
            tpm=100000,
        )
        assert req.chunk_size == 2048
        assert req.trainee_model == "Qwen/Qwen2.5-7B-Instruct"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValidationError):
            GenerateRequest(
                input_file="test.jsonl",
                api_key="sk",
                synthesizer_url="https://api.example.com/v1",
                synthesizer_model="gpt-4",
                mode="invalid_mode",
                data_format="Alpaca",
            )

    def test_invalid_partition_method_raises(self):
        with pytest.raises(ValidationError):
            GenerateRequest(
                input_file="test.jsonl",
                api_key="sk",
                synthesizer_url="https://api.example.com/v1",
                synthesizer_model="gpt-4",
                mode="atomic",
                data_format="Alpaca",
                partition_method="invalid_method",
            )

    def test_negative_chunk_size_raises(self):
        with pytest.raises(ValidationError):
            GenerateRequest(
                input_file="test.jsonl",
                api_key="sk",
                synthesizer_url="https://api.example.com/v1",
                synthesizer_model="gpt-4",
                mode="atomic",
                data_format="Alpaca",
                chunk_size=0,
            )

    def test_negative_rpm_raises(self):
        with pytest.raises(ValidationError):
            GenerateRequest(
                input_file="test.jsonl",
                api_key="sk",
                synthesizer_url="https://api.example.com/v1",
                synthesizer_model="gpt-4",
                mode="atomic",
                data_format="Alpaca",
                rpm=0,
            )

    def test_extra_field_forbidden(self):
        with pytest.raises(ValidationError):
            GenerateRequest(
                input_file="test.jsonl",
                api_key="sk",
                synthesizer_url="https://api.example.com/v1",
                synthesizer_model="gpt-4",
                mode="atomic",
                data_format="Alpaca",
                unknown_field=True,
            )

    def test_missing_input_file_raises(self):
        with pytest.raises(ValidationError):
            GenerateRequest(
                api_key="sk",
                synthesizer_url="https://api.example.com/v1",
                synthesizer_model="gpt-4",
                mode="atomic",
                data_format="Alpaca",
            )

    def test_job_status_pending(self):
        status = JobStatus(
            job_id="abc",
            status="pending",
            created_at="2026-05-03T00:00:00Z",
        )
        assert status.started_at is None
        assert status.progress == 0.0

    def test_progress_out_of_range_raises(self):
        with pytest.raises(ValidationError):
            JobStatus(
                job_id="abc",
                status="pending",
                created_at="2026-05-03T00:00:00Z",
                progress=1.5,
            )

    def test_generate_response(self):
        resp = GenerateResponse(job_id="abc")
        assert resp.status == "pending"
