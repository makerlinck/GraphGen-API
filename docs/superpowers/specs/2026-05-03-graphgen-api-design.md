# Design: GraphGen API Service

**Date:** 2026-05-03
**Status:** Approved
**Type:** New Feature

## Overview

为 GraphGen 拓展纯后端 API 支持，使其可作为独立微服务被 GProject（LLaMA-Factory Workstation）等外部系统调用，完全替代现有 Gradio WebUI 的功能。

## Architecture

### Deployment Context

GraphGen API 作为独立 FastAPI 服务运行，与 GProject 共享 Docker Compose 编排（Redis、MySQL、Celery Workers、GProject Backend/Frontend）。GProject 后端通过 HTTP 调用 GraphGen API 提交数据生成任务。

### Directory Structure

```
api/                          # 新增的 API 子项目
├── __init__.py
├── main.py                   # FastAPI 应用入口 + lifespan
├── server.py                  # 启动入口: python -m api.server
├── config.py                  # Settings (pydantic-settings)
├── routes/
│   ├── __init__.py
│   ├── router.py              # 聚合所有路由
│   ├── health.py              # GET /health
│   ├── connection.py          # POST /test-connection
│   ├── generation.py          # POST /generate, GET /status/{job_id}, GET /output/{job_id}
│   └── files.py               # POST /upload
├── schemas/
│   ├── __init__.py
│   ├── connection.py
│   ├── generation.py
│   └── files.py
├── services/
│   ├── __init__.py
│   ├── pipeline.py            # 流水线编排: 参数→配置→Engine 执行
│   ├── connection.py          # LLM API 连通性测试
│   └── workspace.py           # 工作目录管理
└── job_manager.py             # 任务状态管理 (文件系统持久化)
```

### Layer Responsibilities

- **routes/** — HTTP 端点，参数校验，响应序列化
- **schemas/** — Pydantic 请求/响应模型
- **services/** — 业务逻辑，复用 graphgen 核心包
- **job_manager.py** — 任务生命周期管理，状态文件读写

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | 健康检查 |
| `POST` | `/api/v1/upload` | 上传源文件 |
| `POST` | `/api/v1/test-connection` | 测试 LLM API 连通性 |
| `POST` | `/api/v1/generate` | 提交生成任务（异步） |
| `GET` | `/api/v1/generate/{job_id}/status` | 查询任务状态 |
| `GET` | `/api/v1/generate/{job_id}/output` | 下载生成结果 |

### Schemas

**GenerateRequest** — 包含 WebUI 全部参数：
- 必填: `file_id`, `api_key`, `synthesizer_url`, `synthesizer_model`, `mode`, `data_format`
- 可选: `tokenizer`, `trainee_*`, `chunk_size`, `chunk_overlap`, `quiz_samples`, 分区参数（`partition_method`, `dfs_*`, `bfs_*`, `leiden_*`, `ece_*`）, `rpm`, `tpm`

**JobStatus**:
- `job_id: str`
- `status: str` — `pending | running | done | failed`
- `created_at: str`, `started_at: str | None`, `finished_at: str | None`
- `progress: float | None` — 0.0..1.0
- `error: str | None`
- `output_url: str | None`

**TestConnectionRequest / Response**:
- `{base_url, api_key, model}` → `{success, message}`

**UploadResponse**:
- `{file_id, filename, path}`

## Core Components

### JobManager (`job_manager.py`)

文件系统任务管理，服务重启不丢失状态。

```
cache/jobs/{job_id}/
├── status.json              # 任务状态快照
├── config.yaml              # 保存的流水线配置
└── output/                  # Engine 输出目录（最终结果）
```

状态机: `pending → running → done | failed`

方法: `create()`, `get()`, `update()` — 通过读写 `status.json` 实现。

### PipelineService (`services/pipeline.py`)

从 `GenerateRequest` 参数构造 DAG 配置（从 `webui/app.py` 的 `run_graphgen` 提取抽象），调用 `Engine` 执行。执行期间通过回调更新 `status.json` 进度。

### ConnectionService (`services/connection.py`)

从 `webui/test_api.py` 提取纯业务逻辑（去掉 gradio 依赖），使用 openai SDK 测试 LLM API 连通性。

### WorkspaceService (`services/workspace.py`)

从 `webui/utils/cache.py` 提取 `setup_workspace` / `cleanup_workspace`。

## Data Flow

```
Client (GProject Backend)
     │  POST /api/v1/upload
     ▼
  保存文件到 cache/uploads/
     │  POST /api/v1/generate
     ▼
  JobManager.create() → "pending"
     │  BackgroundTasks.add_task(pipeline.execute)
     ▼
  pipeline.execute()
    ├── "running"
    ├── Engine(config).execute(ds)    # Ray 分布式
    ├── 结果写入 output/
    └── "done" | "failed"
     │  GET /status/{job_id}
     ▼
  JobManager.get() → JobStatus
     │  GET /output/{job_id}
     ▼
  FileResponse → 下载 JSONL
```

## Error Handling

- API 连通性测试失败 → `{success: false, message}` (HTTP 200)
- 参数校验失败 → HTTP 422 (Pydantic)
- 文件/任务不存在 → HTTP 404
- 生成任务异常 → status.json 写为 `failed`，记录 error
- Ray 未初始化 → 健康检查返回异常 (HTTP 503)

## Integration with GProject

GProject 后端在数据准备流程（Phase 2）中通过 `httpx` 调用 GraphGen API：
1. 上传源文件 → `POST /api/v1/upload`
2. 提交生成任务 → `POST /api/v1/generate`
3. 轮询任务状态 → `GET /api/v1/generate/{job_id}/status`
4. 下载结果 → `GET /api/v1/generate/{job_id}/output`

## Constraints

- 复用 `graphgen/` 核心包，不重复实现业务逻辑
- 任务状态持久化到文件系统（无外部数据库依赖）
- GraphGen API 无身份认证（内部服务间调用，Docker 网络隔离）
- 不考虑 Docker 部署配置（本次实现范围外）
