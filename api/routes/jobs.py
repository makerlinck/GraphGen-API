import json
import os

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.config import settings
from api.job_manager import JobManager
from api.schemas.generation import GenerateRequest, GenerateResponse, JobStatus
from api.services.pipeline import execute_pipeline

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _get_manager():
    return JobManager(settings.jobs_dir)


def _resolve_input(input_file: str) -> str:
    """Resolve input_file relative to datasets_dir. Rejects path traversal."""
    datasets = os.path.abspath(settings.datasets_dir)
    os.makedirs(datasets, exist_ok=True)
    resolved = os.path.normpath(os.path.join(datasets, input_file))
    if not resolved.startswith(datasets):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid input_file (path traversal denied): {input_file}",
        )
    return resolved


def _validate_input_file(path: str) -> str | None:
    """Return error message if file is invalid, None if OK."""
    if not os.path.isfile(path):
        return f"Input file not found: {path}"
    if os.path.getsize(path) == 0:
        return f"Input file is empty: {path}"

    ext = os.path.splitext(path)[1].lower()
    if ext in (".json", ".jsonl"):
        return _validate_json_input(path)
    if ext == ".txt":
        with open(path, "r", encoding="utf-8") as f:
            head = f.read(100)
        if not head.strip():
            return f"Input file has no readable content: {path}"

    return None


def _validate_json_input(path: str) -> str | None:
    """Validate JSON/JSONL file has expected content structure."""
    with open(path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
    if not first_line:
        return f"Input file has no content (empty first line): {path}"

    try:
        first_row = json.loads(first_line)
    except json.JSONDecodeError as e:
        return f"Input file has invalid JSON on line 1: {e}"

    if not isinstance(first_row, dict):
        return f"Input file must contain JSON objects, got: {type(first_row).__name__}"

    if "type" not in first_row and "content" not in first_row:
        return (
            f"Input file missing required field. "
            f"Expected 'content' (source text) or 'type' column, "
            f"found: {list(first_row.keys())}"
        )

    return None


@router.post("/jobs", response_model=GenerateResponse, status_code=202)
async def create_job(req: GenerateRequest, background_tasks: BackgroundTasks):
    input_path = _resolve_input(req.input_file)
    error = _validate_input_file(input_path)
    if error:
        raise HTTPException(status_code=422, detail=error)

    manager = _get_manager()
    job_id = manager.create(req.model_dump())
    background_tasks.add_task(execute_pipeline, job_id, req, input_path)
    return GenerateResponse(job_id=job_id)


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    manager = _get_manager()
    try:
        data = manager.get(job_id)
        return JobStatus(**data)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")


@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    manager = _get_manager()
    try:
        data = manager.get(job_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if data["status"] not in ("pending", "running"):
        raise HTTPException(status_code=400, detail="Job already finished")
    manager.update(job_id, status="failed", error="Cancelled by user")
    return {"job_id": job_id, "status": "cancelled"}
