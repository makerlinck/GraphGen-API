# API Config Refactor 缺陷修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复代码审查发现的 8 个问题，覆盖启动崩溃、并发安全、资源泄漏、状态一致性。

**Architecture:** 分四层修复——P0 启动阻断→P1 并发安全→P2 资源泄漏→P3 状态对齐。每层独立可合入，不破坏现有测试。

**Tech Stack:** Python 3.12, Pydantic v2, FastAPI, Ray, threading

---

### Task 1: 修复 MODEL_CONFIG 大写导致的启动崩溃 (P0)

**Files:**
- Modify: `api/config.py:14`

- [ ] **Step 1: 将 MODEL_CONFIG 改回 model_config**

`api/config.py` 第 14 行，`MODEL_CONFIG` 是 Pydantic v2 的保留属性名，全小写才能被元类识别。当前大写导致应用无法导入。

```python
# 修改 api/config.py 第 14 行
# 改前:
    MODEL_CONFIG = {"env_prefix": "GRAPHGEN_"}

# 改后:
    model_config = {"env_prefix": "GRAPHGEN_"}
```

- [ ] **Step 2: 验证导入成功**

运行: `python -c "from api.config import config; print('HOST:', config.HOST); print('PORT:', config.PORT)"`
预期: 成功打印配置值，无报错

- [ ] **Step 3: 验证 env_prefix 生效**

运行: `GRAPHGEN_PORT=9999 python -c "from api.config import config; print('PORT:', config.PORT)"`
预期: `PORT: 9999`（从环境变量读取，非默认 8001）

- [ ] **Step 4: 运行现有测试**

运行: `python -m pytest tests/test_api_routes.py -v`
预期: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add api/config.py
git commit -m "fix: rename MODEL_CONFIG to model_config for Pydantic v2 compatibility

MODEL_CONFIG uppercase is not recognized by Pydantic v2 as model
configuration. This caused a PydanticUserError on import and silently
disabled the GRAPHGEN_ environment variable prefix."
```

---

### Task 2: 修复 pipeline.py 变量遮蔽 (P1)

**Files:**
- Modify: `api/services/pipeline.py:164`

- [ ] **Step 1: 重命名局部变量**

`api/services/pipeline.py` 第 5 行导入了 `from api.config import config`（Config 实例），第 164 行 `config = _build_config(...)` 将其遮蔽为一个字典。目前所有 `config.XXX` 访问都在第 164 行之前，暂无运行时问题，但后续维护极易踩坑。

```python
# 修改 api/services/pipeline.py 第 164 行
# 改前:
    config = _build_config(params, temp_dir, input_path)

# 改后:
    pipeline_cfg = _build_config(params, temp_dir, input_path)
```

- [ ] **Step 2: 更新引用该变量的后续代码**

第 170 行 `engine = Engine(config, operators)` 需要同步修改：

```python
# 改前:
        engine = Engine(config, operators)

# 改后:
        engine = Engine(pipeline_cfg, operators)
```

- [ ] **Step 3: 运行现有测试验证无回归**

运行: `python -m pytest tests/test_api_routes.py -v`
预期: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add api/services/pipeline.py
git commit -m "fix: rename local config variable to avoid shadowing module import

The local variable 'config' in execute_pipeline() shadowed the module-level
import of the Config instance, creating a maintenance hazard for future code
that might access config.XXX after line 164."
```

---

### Task 3: 修复 temp_dir 磁盘泄漏和 Ray 资源泄漏 (P2)

**Files:**
- Modify: `api/services/pipeline.py:140-205`

- [ ] **Step 1: 重写 finally 块**

`api/services/pipeline.py` 第 202-205 行的 `finally` 块仅清理了 engine 引用，没有：
- 删除临时工作目录 `cache/work/{job_id}` 中的中间文件
- 调用 `ray.shutdown()` 释放 Ray actor/worker/共享内存

```python
# 修改 api/services/pipeline.py 第 202-205 行
# 改前:
    finally:
        if engine:
            del engine
        gc.collect()

# 改后:
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
```

- [ ] **Step 2: 验证 Ray 清理逻辑**

Ray 在 `engine.execute()` 被调用后必然处于 initialized 状态。`ray.is_initialized()` 检查确保只在 Ray 确实已初始化时才调用 shutdown，避免在 engine 创建前发生异常时误杀外部 Ray 集群。

- [ ] **Step 3: 运行现有测试**

运行: `python -m pytest tests/test_api_routes.py tests/test_concurrency.py -v`
预期: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add api/services/pipeline.py
git commit -m "fix: clean up temp_dir and Ray resources in pipeline finally block

Previously the finally block only deleted the engine reference. Now it also
calls ray.shutdown() to release Ray actors/workers/shared memory, and removes
the temporary working directory to prevent disk accumulation."
```

---

### Task 4: JobManager 实例锁隔离 —— 全局单例化 (P1)

**Files:**
- Modify: `api/routes/jobs.py:14-15`
- Modify: `api/services/pipeline.py:141`

- [ ] **Step 1: 创建模块级 JobManager 单例工厂**

问题：路由层的 `_get_manager()` 和 `execute_pipeline()` 各自创建独立 `JobManager` 实例，各自的 `_locks` 字典互不可见，导致跨实例的并发更新失去锁保护。

方案：将 `JobManager` 实例提升为模块级单例，所有调用方共享同一个锁字典。

```python
# 修改 api/routes/jobs.py 第 14-15 行
# 改前:
def _get_manager():
    return JobManager(config.JOBS_DIR)

# 改后:
_manager: JobManager | None = None

def _get_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager(config.JOBS_DIR)
    return _manager
```

- [ ] **Step 2: 在 execute_pipeline 中使用同一单例**

```python
# 修改 api/services/pipeline.py 第 140-141 行
# 改前:
def execute_pipeline(job_id: str, params: GenerateRequest, input_path: str):
    manager = JobManager(config.JOBS_DIR)

# 改后:
def execute_pipeline(job_id: str, params: GenerateRequest, input_path: str):
    from api.routes.jobs import _get_manager
    manager = _get_manager()
```

- [ ] **Step 3: 运行并发测试验证线程安全**

运行: `python -m pytest tests/test_concurrency.py::TestJobManagerConcurrency -v`
预期: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add api/routes/jobs.py api/services/pipeline.py
git commit -m "fix: use global JobManager singleton to share per-job locks

Previously each caller created independent JobManager instances with
isolated lock dictionaries. Concurrent updates from the cancel endpoint
and background pipeline could race without mutual exclusion. Now all
callers share a single JobManager and its lock dictionary."
```

---

### Task 5: cancel_job 原子操作和 compare_and_swap (P1)

**Files:**
- Modify: `api/job_manager.py:46-51`
- Modify: `api/routes/jobs.py:98-108`

- [ ] **Step 1: 给 JobManager 添加 compare_and_swap 方法**

当前的 `cancel_job` 在 `get()` 和 `update()` 间释放锁，存在 TOCTOU 窗口。需要原子化的状态条件更新。

```python
# 在 api/job_manager.py 的 JobManager 类中，update 方法之后添加:
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
```

- [ ] **Step 2: 重写 cancel_job 使用 compare_and_swap**

```python
# 修改 api/routes/jobs.py 第 98-108 行
# 改前:
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

# 改后:
@router.delete("/jobs/{job_id}")
async def cancel_job(job_id: str):
    manager = _get_manager()
    now = datetime.now(timezone.utc).isoformat()
    
    cancelled = manager.update_if(
        job_id,
        condition={"status": "pending"},
        updates={"status": "cancelled", "finished_at": now, "error": "Cancelled by user"},
    )
    if cancelled:
        return {"job_id": job_id, "status": "cancelled"}
    
    cancelled = manager.update_if(
        job_id,
        condition={"status": "running"},
        updates={"status": "cancelled", "finished_at": now, "error": "Cancelled by user"},
    )
    if cancelled:
        return {"job_id": job_id, "status": "cancelled"}
    
    # Job is either already done/failed/cancelled, or doesn't exist
    try:
        data = manager.get(job_id)
        return {"job_id": job_id, "status": data["status"]}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
```

需要在文件顶部添加导入:
```python
# 修改 api/routes/jobs.py 第 1-3 行，在 import json 之后添加:
from datetime import datetime, timezone
```

- [ ] **Step 3: 编写 JobManager.update_if 单元测试**

`tests/test_job_manager.py` 不存在，需要在 Task 6 中补充。本步骤仅验证逻辑正确。

运行: `python -m pytest tests/test_api_routes.py -v`
预期: 全部 PASS（现有测试不依赖 cancel 的具体行为）

- [ ] **Step 4: Commit**

```bash
git add api/job_manager.py api/routes/jobs.py
git commit -m "fix: make cancel_job atomic with compare-and-swap

cancel_job previously had a TOCTOU race between get() and update().
Added JobManager.update_if() for atomic conditional updates, ensuring
a finished job cannot be overwritten as 'cancelled' and two concurrent
cancels produce consistent results."
```

---

### Task 6: Schema 对齐 —— 添加 "cancelled" 状态 (P3)

**Files:**
- Modify: `api/schemas/generation.py:54,61`
- Modify: `api/routes/jobs.py:105`

- [ ] **Step 1: 更新 JobStatus schema 添加 "cancelled" 状态**

`cancel_job` 的响应返回 `"cancelled"`，但 `JobStatus` schema 的 `status` Literal 中不包含该值。同时 `GenerateResponse` 的 status 也应匹配完整状态集。

```python
# 修改 api/schemas/generation.py 第 54 行
# 改前:
    status: Literal["pending", "running", "done", "failed"] = "pending"

# 改后:
    status: Literal["pending", "running", "done", "failed", "cancelled"] = "pending"

# 修改 api/schemas/generation.py 第 61 行
# 改前:
    status: Literal["pending", "running", "done", "failed"]

# 改后:
    status: Literal["pending", "running", "done", "failed", "cancelled"]
```

- [ ] **Step 2: 更新文档中的状态流转**

```python
# 修改 docs/api.md 第 167 行
# 改前:
**状态流转：** `pending → running → done | failed`

# 改后:
**状态流转：** `pending → running → done | failed | cancelled`

# 并在表格中添加:
| `cancelled` | 用户取消，`error` 为 "Cancelled by user" |
```

- [ ] **Step 3: 运行测试验证 schema 变更**

运行: `python -m pytest tests/test_api_routes.py -v`
预期: 全部 PASS（现有测试中的 status 断言已使用 `in ("pending", "running", "done", "failed")`，新增 "cancelled" 不影响）

- [ ] **Step 4: Commit**

```bash
git add api/schemas/generation.py docs/api.md
git commit -m "feat: add 'cancelled' status to JobStatus schema

Previously cancel_job returned 'cancelled' in the response but the
JobStatus schema only supported pending/running/done/failed. Added
'cancelled' to the Literal type and updated documentation."
```

---

### Task 7: cancel 检查点 —— 后台任务响应取消 (P2)

**Files:**
- Modify: `api/services/pipeline.py`
- Modify: `api/job_manager.py`

- [ ] **Step 1: 在 execute_pipeline 关键节点添加取消检查**

后台任务在 key 节点检查作业是否已被取消，避免浪费 LLM API 额度。

```python
# 在 api/services/pipeline.py 的 execute_pipeline 函数中，
# 添加辅助函数和检查点。

# 在 execute_pipeline 函数定义之后，try 块内部插入:
def _is_cancelled() -> bool:
    try:
        data = manager.get(job_id)
        return data.get("status") == "cancelled"
    except FileNotFoundError:
        return True

# checkpoint 1: 构建配置后、创建 Engine 前 (第 164 行后)
    if _is_cancelled():
        return _fail(manager, job_id, "Cancelled before pipeline started")

# checkpoint 2: Engine 初始化后、execute 前 (第 172 行后)
    if _is_cancelled():
        return _fail(manager, job_id, "Cancelled before pipeline execution")

# checkpoint 3: checkpoint 2 的修改需要明确插入到正确位置。
# 直接修改 api/services/pipeline.py，在 _setup_env 调用和 manager.update 之间的位置。
```

- [ ] **Step 2: 精确定位插入点并修改**

```python
# 修改 api/services/pipeline.py 第 163-168 行区域:
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
```

```python
# 修改 api/services/pipeline.py 第 170-173 行区域:
    engine = Engine(pipeline_cfg, operators)
    ds = ray.data.from_items([])

    # ── cancellation checkpoint ─────────────────────────────────────────
    try:
        if manager.get(job_id).get("status") == "cancelled":
            return _fail(manager, job_id, "Cancelled before pipeline execution")
    except FileNotFoundError:
        return _fail(manager, job_id, "Job record lost during pipeline")
    # ────────────────────────────────────────────────────────────────────

    manager.update(job_id, progress=0.1)
```

- [ ] **Step 3: 验证 checkpoint 逻辑不破坏正常流程**

运行: `python -m pytest tests/test_api_routes.py tests/test_concurrency.py -v`
预期: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add api/services/pipeline.py
git commit -m "fix: add cancellation checkpoints in pipeline execution

Previously cancel_job only marked the status as cancelled but the
background pipeline continued executing, wasting LLM API calls.
Added checkpoints before Engine creation and before pipeline
execution to bail out early when a job has been cancelled."
```

---

### Task 8: 全量回归测试

**Files:**
- Test: `tests/test_api_routes.py`
- Test: `tests/test_concurrency.py`

- [ ] **Step 1: 运行全部测试**

```bash
python -m pytest tests/test_api_routes.py tests/test_concurrency.py -v --tb=short
```

预期: 全部 PASS

- [ ] **Step 2: 运行导入验证**

```bash
python -c "from api.config import config; from api.routes.jobs import router; from api.services.pipeline import execute_pipeline; print('All imports OK')"
```

预期: `All imports OK`

- [ ] **Step 3: 确认无遗漏的 settings 引用**

```bash
python -m pytest tests/ -v --tb=short
```

预期: 全部 PASS

---

### 执行顺序

```
Task 1 (P0) → Task 2 (P1) → Task 3 (P2) → Task 4 (P1) → Task 5 (P1) → Task 6 (P3) → Task 7 (P2) → Task 8 (回归)
```

Task 1 必须最先执行（解除启动阻塞）。其余任务按依赖关系排列：Task 4 为 Task 5 提供基础（JobManager 单例），Task 5 为 Task 7 提供基础（update_if 方法），Task 6 独立可插入任意位置。
