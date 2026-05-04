from typing import Literal, Optional

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    model_config = {"extra": "forbid"}

    # File I/O — input_file is relative to datasets_dir
    input_file: str

    # LLM
    api_key: str
    synthesizer_url: str
    synthesizer_model: str
    mode: Literal[
        "atomic",
        "multi_hop",
        "aggregated",
        "CoT",
        "multi_choice",
        "multi_answer",
        "fill_in_blank",
        "true_false",
    ]
    data_format: Literal["Alpaca", "Sharegpt", "ChatML"]

    # Optional with defaults
    tokenizer: str = "cl100k_base"
    trainee_model: Optional[str] = None
    trainee_url: Optional[str] = None
    trainee_api_key: Optional[str] = None
    chunk_size: int = Field(default=1024, gt=0)
    chunk_overlap: int = Field(default=100, ge=0)
    quiz_samples: int = Field(default=2, ge=0)
    partition_method: Literal["dfs", "bfs", "leiden", "ece"] = "ece"
    dfs_max_units: int = 5
    bfs_max_units: int = 5
    leiden_max_size: int = 20
    leiden_use_lcc: bool = False
    leiden_random_seed: int = 42
    ece_max_units: int = 20
    ece_min_units: int = 3
    ece_max_tokens: int = 10240
    ece_unit_sampling: Literal["random", "max_loss", "min_loss"] = "random"
    rpm: int = Field(default=1000, gt=0)
    tpm: int = Field(default=50000, gt=0)


class GenerateResponse(BaseModel):
    model_config = {"extra": "forbid"}

    job_id: str
    status: Literal["pending", "running", "done", "failed", "cancelled"] = "pending"


class JobStatus(BaseModel):
    model_config = {"extra": "forbid"}

    job_id: str
    status: Literal["pending", "running", "done", "failed", "cancelled"]
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error: Optional[str] = None
    output_path: Optional[str] = None
