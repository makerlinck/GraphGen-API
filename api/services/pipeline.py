import gc
import os
import traceback
from datetime import datetime, timezone

import ray
from dotenv import load_dotenv

from api.config import config
from api.job_manager import JobManager
from api.schemas.generation import GenerateRequest
from graphgen.engine import Engine
from graphgen.operators import operators
from graphgen.utils import CURRENT_LOGGER_VAR, set_logger

load_dotenv()


def _get_partition_params(params: GenerateRequest) -> dict:
    method = params.partition_method
    if method == "dfs":
        return {"max_units_per_community": params.dfs_max_units}
    if method == "bfs":
        return {"max_units_per_community": params.bfs_max_units}
    if method == "leiden":
        return {
            "max_size": params.leiden_max_size,
            "use_lcc": params.leiden_use_lcc,
            "random_seed": params.leiden_random_seed,
        }
    return {
        "max_units_per_community": params.ece_max_units,
        "min_units_per_community": params.ece_min_units,
        "max_tokens_per_community": params.ece_max_tokens,
        "unit_sampling": params.ece_unit_sampling,
    }


def _build_config(params: GenerateRequest, working_dir: str, input_path: str) -> dict:
    if_trainee = bool(params.trainee_model)

    nodes = [
        {
            "id": "read",
            "op_name": "read",
            "type": "source",
            "dependencies": [],
            "params": {"input_path": [input_path]},
        },
        {
            "id": "chunk",
            "op_name": "chunk",
            "type": "map_batch",
            "dependencies": ["read"],
            "execution_params": {"replicas": 1},
            "params": {
                "chunk_size": params.chunk_size,
                "chunk_overlap": params.chunk_overlap,
            },
        },
        {
            "id": "build_kg",
            "op_name": "build_kg",
            "type": "map_batch",
            "dependencies": ["chunk"],
            "execution_params": {"replicas": 1, "batch_size": 128},
        },
    ]

    last_node_id = "build_kg"

    if if_trainee:
        nodes.append({
            "id": "quiz",
            "op_name": "quiz",
            "type": "aggregate",
            "dependencies": ["build_kg"],
            "execution_params": {"replicas": 1, "batch_size": 128},
            "params": {"quiz_samples": params.quiz_samples, "concurrency_limit": 200},
        })
        nodes.append({
            "id": "judge",
            "op_name": "judge",
            "type": "map_batch",
            "dependencies": ["quiz"],
            "execution_params": {"replicas": 1, "batch_size": 128},
        })
        last_node_id = "judge"

    nodes.append({
        "id": "partition",
        "op_name": "partition",
        "type": "aggregate",
        "dependencies": [last_node_id],
        "params": {
            "method": params.partition_method,
            "method_params": _get_partition_params(params),
        },
    })

    nodes.append({
        "id": "generate",
        "op_name": "generate",
        "type": "map_batch",
        "dependencies": ["partition"],
        "save_output": True,
        "execution_params": {"replicas": 1, "batch_size": 128},
        "params": {
            "method": params.mode,
            "data_format": params.data_format,
        },
    })

    return {
        "global_params": {
            "working_dir": working_dir,
            "graph_backend": "kuzu",
            "kv_backend": "rocksdb",
        },
        "nodes": nodes,
    }


def _setup_env(params: GenerateRequest):
    os.environ["SYNTHESIZER_BACKEND"] = "openai_api"
    os.environ["SYNTHESIZER_BASE_URL"] = params.synthesizer_url
    os.environ["SYNTHESIZER_API_KEY"] = params.api_key
    os.environ["SYNTHESIZER_MODEL"] = params.synthesizer_model
    os.environ["RPM"] = str(params.rpm)
    os.environ["TPM"] = str(params.tpm)
    os.environ["TOKENIZER_MODEL"] = params.tokenizer

    if params.trainee_model:
        os.environ["TRAINEE_BACKEND"] = "openai_api"
        os.environ["TRAINEE_BASE_URL"] = params.trainee_url or ""
        os.environ["TRAINEE_API_KEY"] = params.trainee_api_key or ""
        os.environ["TRAINEE_MODEL"] = params.trainee_model


def execute_pipeline(job_id: str, params: GenerateRequest, input_path: str):
    from api.routes.jobs import _get_manager
    manager = _get_manager()
    now = datetime.now(timezone.utc).isoformat()

    # output: automatically saved as {datasets_dir}/{job_id}.jsonl
    datasets_dir = os.path.abspath(config.DATASETS_DIR)
    os.makedirs(datasets_dir, exist_ok=True)
    output_path = os.path.join(datasets_dir, f"{job_id}.jsonl")

    manager.update(job_id, status="running", started_at=now, progress=0.0)

    # ── validate input ──────────────────────────────────────────────────
    if not os.path.isfile(input_path):
        return _fail(manager, job_id, f"Input file not found: {input_path}")

    # ── setup workspace ──────────────────────────────────────────────────
    temp_dir = os.path.join(config.CACHE_DIR, "work", job_id)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(config.LOG_DIR, exist_ok=True)
    log_file = os.path.join(config.LOG_DIR, f"{job_id}.log")
    driver_logger = set_logger(log_file, "GraphGen", if_stream=True)
    CURRENT_LOGGER_VAR.set(driver_logger)

    _setup_env(params)
    pipeline_cfg = _build_config(params, temp_dir, input_path)

    # ── cancellation checkpoint ─────────────────────────────────────────
    try:
        if manager.get(job_id).get("status") == "cancelled":
            return _fail(manager, job_id, "Cancelled before pipeline started")
    except FileNotFoundError:
        return _fail(manager, job_id, "Job record lost before pipeline started")
    # ────────────────────────────────────────────────────────────────────

    # ── run pipeline ─────────────────────────────────────────────────────
    manager.update(job_id, progress=0.05)
    engine = None
    try:
        engine = Engine(pipeline_cfg, operators)
        ds = ray.data.from_items([])

        # ── cancellation checkpoint ─────────────────────────────────────
        try:
            if manager.get(job_id).get("status") == "cancelled":
                return _fail(manager, job_id, "Cancelled before pipeline execution")
        except FileNotFoundError:
            return _fail(manager, job_id, "Job record lost during pipeline")
        # ────────────────────────────────────────────────────────────────

        manager.update(job_id, progress=0.1)

        results = engine.execute(ds, output_dir=temp_dir)

        manager.update(job_id, progress=0.85)

        row_count = _collect_and_save(results, temp_dir, output_path)

        if row_count == 0:
            return _fail(
                manager, job_id,
                "Pipeline completed but generated 0 rows. "
                "Possible causes: input too short, LLM API error, "
                "or knowledge graph too sparse."
            )

        manager.update(
            job_id,
            status="done",
            finished_at=datetime.now(timezone.utc).isoformat(),
            progress=1.0,
            output_path=output_path,
        )

    except Exception:
        return _fail(
            manager, job_id,
            f"Pipeline error: {traceback.format_exc()}"
        )
    finally:
        if engine:
            del engine
        gc.collect()
        # Release Ray resources (actors, workers, shared memory)
        if ray.is_initialized():
            try:
                ray.shutdown()
            except Exception:
                pass
        # Clean up temporary working directory
        import shutil
        if os.path.isdir(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass


def _fail(manager, job_id, error: str):
    manager.update(
        job_id,
        status="failed",
        finished_at=datetime.now(timezone.utc).isoformat(),
        error=error,
    )


def _collect_and_save(results: dict, temp_dir: str, output_path: str) -> int:
    """Collect generated JSONL and save to output path. Returns row count."""
    import json

    generate_dir = os.path.join(temp_dir, "generate")
    if not os.path.isdir(generate_dir):
        raise RuntimeError(
            "Generation step produced no output. "
            "The 'generate' directory was not created."
        )

    jsonl_files = sorted(
        f for f in os.listdir(generate_dir) if f.endswith(".jsonl")
    )
    if not jsonl_files:
        raise RuntimeError(
            "Generation step produced no JSONL files. "
            "The generate node may have failed silently."
        )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    row_count = 0
    with open(output_path, "w", encoding="utf-8") as out:
        for fname in jsonl_files:
            filepath = os.path.join(generate_dir, fname)
            with open(filepath, "r", encoding="utf-8") as inf:
                for line in inf:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        json.loads(line)
                    except json.JSONDecodeError as e:
                        raise RuntimeError(
                            f"Generated output contains invalid JSON "
                            f"in {fname}: {e}"
                        )
                    out.write(line + "\n")
                    row_count += 1

    return row_count
