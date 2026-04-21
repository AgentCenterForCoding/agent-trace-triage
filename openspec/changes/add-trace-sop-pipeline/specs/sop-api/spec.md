## 新增需求

### 需求:暴露 SOP 检索 HTTP 端点

系统必须在后端 FastAPI 应用中注册路由 `GET /api/v1/sops/retrieve`，接受下列 query 参数：
- `user_id`（必填，字符串）：OS 用户名。
- `query`（可选，字符串）：用于 tags/关键词匹配的任务描述文本。
- `k`（可选，整数，默认 3，取值范围 1–10）。
- `include_disabled`（可选，布尔，默认 `false`）。

端点内部调用 `sop-registry.retrieve(user_id, query, k, include_disabled=include_disabled)` 并返回 JSON。端点必须注册在 `/api/v1` 前缀下，沿用后端既有路由惯例。

#### 场景:正常检索
- **当** 客户端以合法参数请求 `GET /api/v1/sops/retrieve?user_id=alice&k=3`
- **那么** 系统返回 200 与 JSON 数组，每个元素包含 `meta`（SOP 元信息对象）与 `body`（Markdown 正文字符串）

#### 场景:缺少必填参数
- **当** 请求未提供 `user_id` 或 `user_id` 为空字符串
- **那么** 系统返回 422 Unprocessable Entity，body 含 FastAPI 标准校验错误结构

#### 场景:k 超出范围
- **当** 请求 `k=0` 或 `k=100`
- **那么** 系统返回 422

### 需求:路径穿越翻译为 403

系统必须将 `sop-registry` 抛出的 `PermissionError`（源于路径穿越尝试）在 API 层统一翻译为 HTTP 403 Forbidden，不得将异常栈或内部路径信息泄露到响应 body。

#### 场景:路径穿越被拦截
- **当** 请求 `user_id="../other"` 导致 registry 抛 `PermissionError`
- **那么** 系统返回 403 与简明错误消息（形如 `{"detail": "invalid user_id"}`），不泄露内部路径

### 需求:沿用既有 API Key 鉴权

系统必须让 `/api/v1/sops/*` 路由经过 `backend.main` 既有的 `api_key_auth` 中间件；当 `get_settings().auth_enabled` 为 `true` 时，请求必须携带合法 `X-API-Key` 头，否则返回 401。

#### 场景:鉴权开启且缺少 Key
- **当** `auth_enabled=true` 且请求未带 `X-API-Key`
- **那么** 系统返回 401 Unauthorized（由 `api_key_auth` 中间件产生）

#### 场景:鉴权关闭
- **当** `auth_enabled=false`
- **那么** 请求无需 `X-API-Key` 即可访问 `/api/v1/sops/retrieve`

### 需求:响应体结构稳定

系统必须保证响应 JSON 结构稳定以便 Hook CLI 与未来 Web UI 解析：顶层为数组，元素为对象 `{"meta": {...}, "body": "..."}`；`meta` 对象字段与 `sop-registry` 中的 `SOPMeta` 一致。空结果返回 `[]` 而非 `null`。

#### 场景:零结果
- **当** 当前 `user_id` 下没有任何启用的 SOP
- **那么** 系统返回 200 与 body `[]`

#### 场景:meta 字段完整
- **当** 响应 body 非空
- **那么** 每条元素的 `meta` 必须含 `id`、`name`、`version`、`enabled`、`tags`、`created`、`updated`、`source_trace_ids`、`confidence`、`needs_review`、`conflict_with` 全部字段

## 修改需求
<!-- 无 -->

## 移除需求
<!-- 无 -->
