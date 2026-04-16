## 新增需求

### 需求:SSE 归因接口
系统必须提供 SSE 归因 API，实时推送分析进度和最终结果。

#### 场景:SSE 归因成功
- **当** 客户端 POST 请求 /api/v1/triage，body 包含有效的 Trace JSON
- **那么** 系统返回 SSE 流，依次推送 progress 事件和最终 result 事件

#### 场景:进度推送
- **当** 归因过程中
- **那么** SSE 推送 `event: progress`，data 包含 stage 和 message

#### 场景:最终结果
- **当** 归因完成
- **那么** SSE 推送 `event: result`，data 包含完整的 TriageResult JSON

#### 场景:Trace 格式错误
- **当** 客户端提交格式错误的 Trace
- **那么** SSE 推送 `event: error`，data 包含错误详情

#### 场景:OpenCode CLI 调用失败
- **当** `opencode run` 进程异常退出
- **那么** SSE 推送 `event: error`，data 包含错误信息

### 需求:异步归因接口（MVP）
系统提供简单的异步归因 API，任务状态存储在内存中。

#### 场景:提交异步任务
- **当** 客户端 POST 请求 /api/v1/triage/async
- **那么** 系统返回 202 状态码和 task_id

#### 场景:查询任务状态
- **当** 客户端 GET 请求 /api/v1/triage/{task_id}
- **那么** 系统返回任务状态（pending/processing/completed/failed）和结果（如已完成）

#### 场景:服务重启后任务丢失
- **当** 服务重启后查询之前的 task_id
- **那么** 系统返回 404（内存存储限制，文档标注）

### 需求:API Key 管理
系统支持通过 API 管理认证密钥，密钥在 UI 配置并持久化到文件。

#### 场景:配置 API Key
- **当** 客户端 POST 请求 /api/v1/settings/api-key，body 包含 key
- **那么** 系统将 key 存储到 config/settings.json

#### 场景:有效 API Key
- **当** 认证已启用且请求 Header 包含有效的 X-API-Key
- **那么** 系统正常处理请求

#### 场景:认证未配置
- **当** 未配置任何 API Key（默认状态）
- **那么** 系统跳过认证，直接处理请求

#### 场景:无效 API Key
- **当** 认证已启用且请求缺少 X-API-Key 或 Key 无效
- **那么** 系统返回 401 状态码

### 需求:静态文件托管
Backend 必须托管前端 React 构建产物。

#### 场景:访问前端页面
- **当** 客户端 GET 请求 / 或 /index.html
- **那么** 系统返回 React 应用的 index.html

#### 场景:前端路由回退
- **当** 客户端 GET 请求非 /api/ 开头的路径
- **那么** 系统返回 index.html（支持前端路由）

### 需求:样本 Trace 列表
系统提供样本 Trace 文件列表供前端展示。

#### 场景:获取样本列表
- **当** 客户端 GET 请求 /api/v1/samples
- **那么** 系统返回 sample_traces/ 目录下的文件名列表

#### 场景:获取样本内容
- **当** 客户端 GET 请求 /api/v1/samples/{filename}
- **那么** 系统返回对应的 Trace JSON 内容

## 修改需求

## 移除需求
