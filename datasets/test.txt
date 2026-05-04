# GProject API 文档

**Base URL:** `http://127.0.0.1:8000`

---

## 认证说明

除「公开端点」外，所有 `/api/` 下接口需在请求头携带 JWT：

```
Authorization: Bearer <access_token>
```

access_token 通过登录接口获取，有效期 1 小时；refresh_token 有效期 7 天。

---

## 公开端点

### `GET /health`

服务存活检测。

**响应 200:**

```json
{ "app": "GProject", "status": "running", "mysql": "connected" }
```

`mysql` 为 `"connected"` 或 `"unavailable"`。

---

### `GET /api/v1/`

API 版本信息。

**响应 200:**

```json
{ "api_version": "v1", "status": "ok" }
```

---

### `GET /down_dataset/{token}`

凭下载令牌获取数据集文件。

令牌从 `POST /api/v1/dataset/{id}/download` 获取，有效期 15 分钟，无需额外认证头。

**响应 200:** `application/octet-stream` 文件流

**响应 401:**
```json
{ "error": "Invalid or expired download token." }
```

**响应 404:**
```json
{ "error": "Dataset not found: 1" }
```

---

## 认证

### `POST /api/v1/auth/login`

用户登录，返回 JWT token 对。

**请求体:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| email | string | 是 | 登录邮箱 |
| password | string | 是 | 明文密码 |
| login_ip | string | 否 | 客户端 IP |

**请求示例:**

```json
{
  "email": "alice@test.com",
  "password": "secret123"
}
```

**响应 200 (成功):**

```json
{
  "user_id": 1,
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "expires_in": 3600,
  "success": true,
  "error": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | int \| null | 用户 ID |
| access_token | string \| null | JWT 访问令牌 (1h) |
| refresh_token | string \| null | JWT 刷新令牌 (7d) |
| expires_in | int \| null | access_token 有效期（秒） |
| success | bool | 是否成功 |
| error | string \| null | 失败时的错误信息 |

---

## 用户

### `GET /api/v1/user`

获取当前用户信息（不含密码）。需 `Authorization: Bearer <access_token>`。

**响应 200:**

```json
{
  "id": 1,
  "name": "alice",
  "email": "alice@test.com",
  "is_admin": false,
  "is_active": true,
  "created_at": "2026-05-01T10:00:00",
  "last_login": "2026-05-02T15:30:00",
  "error": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 用户 ID |
| name | string | 用户名 |
| email | string | 邮箱 |
| is_admin | bool | 是否管理员 |
| is_active | bool | 是否激活 |
| created_at | datetime | 创建时间 |
| last_login | datetime | 最后登录时间 |
| error | string \| null | 错误信息 |

---

### `POST /api/v1/user`

注册新用户。

**请求体:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 用户名 |
| email | string | 是 | 邮箱（唯一） |
| password | string | 是 | 密码（≥8 位，至少包含大小写/数字/特殊字符中的 2 类） |

**请求示例:**

```json
{
  "name": "alice",
  "email": "alice@test.com",
  "password": "Str0ng!Pass"
}
```

**响应 200 (成功):**

```json
{
  "user_id": 1,
  "name": "alice",
  "email": "alice@test.com",
  "success": true,
  "error": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | int \| null | 新用户 ID |
| name | string \| null | 用户名 |
| email | string \| null | 邮箱 |
| success | bool | 是否成功 |
| error | string \| null | 错误信息 |

---

## 数据集

所有数据集端点均需 `Authorization: Bearer <access_token>`。

### `GET /api/v1/dataset/`

返回当前用户的数据集列表（按 token owner_id 过滤）。

**响应 200:**

```json
{
  "items": [
    {
      "id": 1,
      "owner_id": 1,
      "name": "训练数据集",
      "desc": "用于微调的数据集",
      "meta": {
        "format": "json",
        "file_path": "/datafile/datasets/a1b2c3d4.json",
        "file_size": 1048576
      },
      "status": 0,
      "tag_ids": [1, 2],
      "created_at": "2026-05-01T10:00:00",
      "updated_at": "2026-05-02T15:30:00"
    }
  ],
  "total": 1,
  "error": null
}
```

---

### `GET /api/v1/dataset/{id}`

返回单个数据集详情（仅限所属用户，非所属返回 Access denied）。

**响应 200:**

```json
{
  "dataset": {
    "id": 1,
    "owner_id": 1,
    "name": "训练数据集",
    "meta": { "format": "json", "file_path": "/data/a1b2c3d4.json", "file_size": 1048576 },
    "status": 0,
    "tag_ids": [],
    "created_at": "2026-05-01T10:00:00",
    "updated_at": "2026-05-02T15:30:00"
  },
  "error": null
}
```

**错误响应:**

```json
{ "dataset": null, "error": "Access denied to dataset: 1" }
```

---

### `POST /api/v1/dataset/upload/initiate`

初始化分块上传。

**请求体:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| filename | string | 是 | 原始文件名 |
| file_size | int | 是 | 文件总大小（字节） |
| file_hash | string | 是 | 文件 SHA-256 |
| chunk_size | int | 否 | 分片大小（默认 5MB，1-10MB） |

**响应 200:**

```json
{
  "upload_id": "a1b2c3d4e5f6",
  "chunk_size": 5242880,
  "total_chunks": 3,
  "uploaded_chunks": [],
  "is_instant_complete": false
}
```

---

### `POST /api/v1/dataset/upload/chunk`

上传单个分片 (multipart/form-data)。

**表单字段:**

| 字段 | 类型 | 说明 |
|------|------|------|
| upload_id | string | 上传会话 ID |
| chunk_index | int | 分片序号 (0-based) |
| file | binary | 分片数据 |

**响应 200:**

```json
{ "upload_id": "a1b2c3d4e5f6", "chunk_index": 0, "received": true }
```

---

### `GET /api/v1/dataset/upload/{upload_id}/status`

查询上传进度（断点续传）。

**响应 200:**

```json
{
  "upload_id": "a1b2c3d4e5f6",
  "uploaded_chunks": [0, 2],
  "total_chunks": 3,
  "is_complete": false
}
```

---

### `POST /api/v1/dataset/upload/complete`

合并分块 → SHA-256 校验 → 创建 Dataset 记录。文件存为 `datasets/{id}.{ext}`。

**请求体:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| upload_id | string | 是 | 上传会话 ID |
| owner_id | int | 是 | 所属用户（路由层从 token 注入） |
| name | string | 是 | 数据集名称 |
| desc | string | 否 | 描述 |
| tag_ids | int[] | 否 | 标签 ID |

**响应 200:**

```json
{
  "dataset_id": 1,
  "file_path": "/path/to/datasets/1.json",
  "success": true
}
```

**错误:**

```json
{ "dataset_id": null, "file_path": "", "success": false, "error": "Hash mismatch..." }
```

---

### `GET /api/v1/dataset/{id}/sample`

获取数据集前 N 条样本及表头（用于数据预处理 Step 2 的字段映射预览）。

**查询参数:**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 100 | 返回行数 (1-200) |

**响应 200:**

```json
{
  "columns": ["question", "answer", "category"],
  "rows": [
    { "question": "什么是机器学习？", "answer": "机器学习是...", "category": "AI" }
  ],
  "total_rows": 50000,
  "error": null
}
```

---

### `POST /api/v1/dataset/{id}/process`

提交数据清洗或格式转换任务。配置提交后由 Celery 异步执行，返回 task_id 用于进度追踪。

**请求体 (清洗 clean):**

```json
{
  "process_type": "clean",
  "clean_config": {
    "field_mapping": [
      { "source_column": "question", "target_field": "instruction" },
      { "source_column": "answer",   "target_field": "output" }
    ],
    "basic_filtering": {
      "enabled": true,
      "remove_empty": true,
      "min_text_length": 10
    },
    "text_formatting": {
      "enabled": true,
      "remove_html": true,
      "normalize_unicode": false
    },
    "pii_masking": {
      "enabled": true,
      "phone": true,
      "id_card": false,
      "email": true,
      "bank_card": false
    },
    "deduplication": {
      "enabled": true,
      "method": "minhash",
      "threshold": 0.85
    }
  }
}
```

**请求体 (格式转换 convert):**

```json
{
  "process_type": "convert",
  "convert_format": "alpaca"
}
```

**ProcessRequest 字段:**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| process_type | `"clean"` \| `"convert"` | 是 | 处理类型 |
| clean_config | CleanConfig | type=clean 时必填 | 清洗编排配置 |
| convert_format | `"alpaca"` \| `"sharegpt"` | type=convert 时必填 | 转换目标格式 |

**CleanConfig 子配置:**

| 算子 | 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|------|
| **field_mapping** | | | | **字段映射 (LLaMA 标准三字段)** |
| | source_column | string | — | 源数据表头名 |
| | target_field | instruction / input / output | — | LLaMA-Factory 标准字段 |
| **basic_filtering** | | | | **基础过滤** |
| | enabled | bool | false | 启用 |
| | remove_empty | bool | true | 剔除空白行/缺失值 |
| | min_text_length | int | 10 | 短文本过滤阈值 |
| **text_formatting** | | | | **文本格式化** |
| | enabled | bool | false | 启用 |
| | remove_html | bool | true | 移除 HTML/XML 标签 |
| | normalize_unicode | bool | false | 全角转半角 |
| **pii_masking** | | | | **隐私脱敏** |
| | enabled | bool | false | 启用 |
| | phone | bool | true | 手机号脱敏 |
| | id_card | bool | false | 身份证号脱敏 |
| | email | bool | false | 邮箱脱敏 |
| | bank_card | bool | false | 银行卡号脱敏 |
| **deduplication** | | | | **语料去重** |
| | enabled | bool | false | 启用 |
| | method | exact / minhash | minhash | 去重算法 |
| | threshold | float (0.5-1.0) | 0.85 | MinHash 相似度阈值 |

**响应 200:**

```json
{
  "task_id": "cln_9fa82b",
  "status": "pending",
  "message": "Task started",
  "error": null
}
```

---

### `POST /api/v1/dataset/{id}/download`

生成下载令牌。

**响应 200:**

```json
{
  "download_token": "eyJhbGciOiJIUzI1NiIs...",
  "filename": "training_data.json",
  "file_size": 1048576,
  "format": "json"
}
```

获取令牌后，通过 `GET /down_dataset/{token}` 下载实际文件。

---

### `DELETE /api/v1/dataset/{id}`

删除数据集（含数据库记录和服务器文件）。

**响应 200 (成功):**

```json
{ "deleted": "1" }
```

**响应 200 (失败):**

```json
{ "error": "Dataset not found: 1" }
```

---

## 端点索引

| 方法 | 路径 | 认证 | 状态 |
|------|------|:--:|:--:|
| `GET` | `/health` | — | ✅ |
| `GET` | `/api/v1/` | — | ✅ |
| `GET` | `/down_dataset/{token}` | 令牌 | ✅ |
| `POST` | `/api/v1/auth/login` | — | ✅ |
| `GET` | `/api/v1/user` | Bearer | ✅ |
| `POST` | `/api/v1/user` | — | ✅ |
| `GET` | `/api/v1/dataset/` | Bearer | ✅ |
| `GET` | `/api/v1/dataset/{id}` | Bearer | ✅ |
| `POST` | `/api/v1/dataset/upload/initiate` | Bearer | ✅ |
| `POST` | `/api/v1/dataset/upload/chunk` | Bearer | ✅ |
| `GET` | `/api/v1/dataset/upload/{id}/status` | Bearer | ✅ |
| `POST` | `/api/v1/dataset/upload/complete` | Bearer | ✅ |
| `GET` | `/api/v1/dataset/{id}/sample` | Bearer | ⚠️ 占位 |
| `POST` | `/api/v1/dataset/{id}/process` | Bearer | ✅ Celery |
| `POST` | `/api/v1/dataset/{id}/download` | Bearer | ✅ |
| `DELETE` | `/api/v1/dataset/{id}` | Bearer | ✅ |
