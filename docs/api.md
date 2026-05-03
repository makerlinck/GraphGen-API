# GraphGen API

纯后端数据生成服务，基于 GraphGen 知识图谱合成数据流水线。

## 启动

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8001
```

默认从 `./datasets/` 读取输入文件，输出文件自动命名为 `{job_id}.jsonl` 写入同目录。

可通过环境变量覆盖：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `GRAPHGEN_HOST` | `0.0.0.0` | 监听地址 |
| `GRAPHGEN_PORT` | `8001` | 监听端口 |
| `GRAPHGEN_DATASETS_DIR` | `datasets` | 输入/输出目录 |

## 端点

### `GET /health`

健康检查。

```json
// 200
{"status": "ok"}
```

---

### `POST /api/v1/connections/validate`

测试 LLM API 连通性。

**请求：**

```json
{
    "base_url": "https://api.siliconflow.cn/v1",
    "api_key": "sk-xxxxxx",
    "model": "Qwen/Qwen2.5-7B-Instruct"
}
```

**响应：**

```json
// 200
{"success": true, "message": "Qwen/Qwen2.5-7B-Instruct: API connection successful"}
```

---

### `POST /api/v1/jobs`

提交数据生成任务。输入文件需预先放入 `datasets/` 目录。

**请求：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `input_file` | `string` | 是 | 输入文件名，相对于 `datasets/` 目录 |
| `api_key` | `string` | 是 | LLM API Key |
| `synthesizer_url` | `string` | 是 | LLM API 地址 |
| `synthesizer_model` | `string` | 是 | 合成模型名称 |
| `mode` | `string` | 是 | 生成模式 |
| `data_format` | `string` | 是 | 输出格式 |
| `tokenizer` | `string` | 否 | 分词器，默认 `cl100k_base` |
| `trainee_model` | `string` | 否 | 训练目标模型（启用 Quiz & Judge） |
| `trainee_url` | `string` | 否 | 训练目标模型 API 地址 |
| `trainee_api_key` | `string` | 否 | 训练目标模型 API Key |
| `chunk_size` | `int` | 否 | 分块大小，默认 1024 |
| `chunk_overlap` | `int` | 否 | 分块重叠，默认 100 |
| `quiz_samples` | `int` | 否 | Quiz 采样数，默认 2 |
| `partition_method` | `string` | 否 | 图分区算法：`dfs`/`bfs`/`leiden`/`ece`，默认 `ece` |
| `dfs_max_units` | `int` | 否 | DFS 每社区最大单元数，默认 5 |
| `bfs_max_units` | `int` | 否 | BFS 每社区最大单元数，默认 5 |
| `leiden_max_size` | `int` | 否 | Leiden 社区最大大小，默认 20 |
| `leiden_use_lcc` | `bool` | 否 | 使用最大连通分量，默认 false |
| `leiden_random_seed` | `int` | 否 | Leiden 随机种子，默认 42 |
| `ece_max_units` | `int` | 否 | ECE 每社区最大单元数，默认 20 |
| `ece_min_units` | `int` | 否 | ECE 每社区最小单元数，默认 3 |
| `ece_max_tokens` | `int` | 否 | ECE 每社区最大 Token 数，默认 10240 |
| `ece_unit_sampling` | `string` | 否 | ECE 采样策略：`random`/`max_loss`/`min_loss`，默认 `random` |
| `rpm` | `int` | 否 | 每分钟请求数限制，默认 1000 |
| `tpm` | `int` | 否 | 每分钟 Token 数限制，默认 50000 |

**`mode` 可选值：**

| 值 | 说明 |
|------|------|
| `atomic` | 原子问答对 |
| `multi_hop` | 多跳推理问答对 |
| `aggregated` | 聚合知识问答对 |
| `CoT` | 思维链问答对 |
| `multi_choice` | 选择题 |
| `multi_answer` | 多选题 |
| `fill_in_blank` | 填空题 |
| `true_false` | 判断题 |

**`data_format` 可选值：** `Alpaca` / `Sharegpt` / `ChatML`

**示例：**

```json
{
    "input_file": "my_document.jsonl",
    "api_key": "sk-xxxxxx",
    "synthesizer_url": "https://api.siliconflow.cn/v1",
    "synthesizer_model": "Qwen/Qwen2.5-7B-Instruct",
    "mode": "atomic",
    "data_format": "Alpaca"
}
```

**响应：**

```json
// 202 Accepted
{"job_id": "a1b2c3d4-...", "status": "pending"}
```

**输入文件格式：**

JSONL 每行一个对象，需包含 `content`（源文本）或 `type` 字段：

```jsonl
{"content": "Photosynthesis is the process by which green plants convert sunlight into chemical energy."}
{"content": "Machine learning is a subset of artificial intelligence."}
```

纯文本 `.txt` 文件也支持。

**前置校验：**

请求在创建任务前会校验：
- 文件存在且非空
- JSON 格式有效
- 包含 `content` 或 `type` 字段
- 无路径穿越攻击

---

### `GET /api/v1/jobs/{job_id}`

查询任务状态。

**响应：**

```json
// 200
{
    "job_id": "a1b2c3d4-...",
    "status": "running",
    "created_at": "2026-05-03T12:00:00+00:00",
    "started_at": "2026-05-03T12:00:01+00:00",
    "finished_at": null,
    "progress": 0.35,
    "error": null,
    "output_path": null
}
```

**状态流转：** `pending → running → done | failed`

| status | 说明 |
|--------|------|
| `pending` | 已提交，等待执行 |
| `running` | 执行中，`progress` 递增 (0.0 → 1.0) |
| `done` | 完成，`output_path` 指向输出文件 |
| `failed` | 失败，`error` 包含错误信息 |

---

### `DELETE /api/v1/jobs/{job_id}`

取消正在执行的任务。

```json
// 200
{"job_id": "a1b2c3d4-...", "status": "cancelled"}
```

---

## 完整示例

```powershell
# 准备输入
'{"content": "Artificial intelligence is transforming industries."}' | Out-File -Encoding utf8 datasets/input.jsonl

# 提交
$body = @{
    input_file = "input.jsonl"
    api_key = "sk-xxxxxx"
    synthesizer_url = "https://api.siliconflow.cn/v1"
    synthesizer_model = "Qwen/Qwen2.5-7B-Instruct"
    mode = "atomic"
    data_format = "Alpaca"
} | ConvertTo-Json

$job = Invoke-RestMethod -Uri http://localhost:8001/api/v1/jobs -Method Post -Body $body -ContentType "application/json"

# 轮询
do {
    Start-Sleep 5
    $status = Invoke-RestMethod -Uri "http://localhost:8001/api/v1/jobs/$($job.job_id)"
    Write-Host "$($status.status) progress=$($status.progress)"
} while ($status.status -eq 'pending' -or $status.status -eq 'running')

# 输出在 datasets/{job_id}.jsonl
Get-Content "datasets/$($job.job_id).jsonl"
```

## 错误码

| 状态码 | 说明 |
|--------|------|
| 200 | 成功 |
| 202 | 任务已提交 |
| 404 | 任务不存在 |
| 422 | 参数校验失败或输入文件无效 |
| 500 | 服务内部错误 |
