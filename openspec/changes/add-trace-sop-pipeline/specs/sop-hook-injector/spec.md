## 新增需求

### 需求:提供 OpenCode `session.start` Hook 可调用的 CLI 入口

系统必须提供一个独立的命令行入口（`python -m backend.sop.hook_cli`，并附 Windows `.cmd` 与 Unix `.sh` 包装脚本），可被 OpenCode CLI 在 `session.start` Hook 阶段调用。该入口从环境变量读取 `user_id`（优先 `AGENT_TRIAGE_USER`，缺省回落 `os.getlogin()`），完成后将 SOP Markdown 写入 stdout 并以退出码 0 结束。stderr 仅用于日志与告警，不会被 OpenCode 拼入上下文。

#### 场景:正常 Hook 调用
- **当** OpenCode 在 `session.start` 阶段调用 Hook CLI 且可正常解析 `user_id`
- **那么** 系统检索 top-K SOP 并将其 Markdown 正文写入 stdout，以退出码 0 结束

#### 场景:无法解析 user_id
- **当** `AGENT_TRIAGE_USER` 未设置且 `os.getlogin()` 抛错
- **那么** 系统以退出码 2 结束，stdout 不输出任何内容（防止将错误信息误拼入上下文），stderr 输出错误说明

### 需求:通过 HTTP 调用后端 API 检索 SOP

系统必须以 HTTP 客户端形式调用 `GET {AGENT_TRIAGE_API_URL}/api/v1/sops/retrieve?user_id=<user>&k=3`（`AGENT_TRIAGE_API_URL` 缺省为 `http://localhost:3014`），禁止直接读取 `backend/data/sops/` 文件。请求必须设 500ms 连接+读取超时。若 `AGENT_TRIAGE_API_KEY` 环境变量已设置，必须在请求头带 `X-API-Key`。

#### 场景:正常检索
- **当** 后端 API 返回 200 与 SOP 列表 JSON
- **那么** 系统解析响应并提取每条 SOP 的 Markdown 正文

#### 场景:后端不可达静默降级
- **当** HTTP 请求发生 ConnectionRefused、超时或返回非 2xx 状态
- **那么** 系统以退出码 0 结束、stdout 为空，并在 stderr 记录一行告警，绝不让 OpenCode 会话启动失败

### 需求:注入内容强制携带显式 SOP 标记头

系统必须在 stdout 输出的第一行写入固定标记头 `--- AgentTriage SOP Suggestions (非强制执行，仅供参考) ---`，在末尾写入对应结束标记 `--- End of SOP Suggestions ---`。任何情况下禁止将 SOP 正文直接暴露为"指令"形式（例如禁止在 SOP 前加上"请立即执行以下步骤"等诱导性前缀）。

#### 场景:检索到 SOP
- **当** API 返回 2 条 SOP
- **那么** 系统输出：起始标记头 → 第一条 SOP 正文 → 分隔空行 → 第二条 SOP 正文 → 结束标记

#### 场景:检索无结果
- **当** API 返回空列表
- **那么** 系统输出空 stdout（不写标记头也不写结束标记），退出码 0

### 需求:注入规模与延迟硬限制

系统必须保证单次注入的 top-K 上限为 3、注入总字节数上限为 8KB（含标记头与结束标记）。若累计字节数超过 8KB，必须按相关度顺序丢弃低优先级 SOP 正文直到满足上限，并在 stderr 记录 `dropped N by byte cap`。CLI 入口从启动到写完 stdout 的 P99 延迟必须 < 200ms（在本地 50 条 SOP 规模下，含 localhost HTTP 往返）；单次调用超过 500ms 时在 stderr 记录告警（不影响 stdout 输出）。

#### 场景:命中字节上限
- **当** top-3 SOP Markdown 累计 12KB
- **那么** 系统只输出按相关度排序能塞下的前若干条，累计不超过 8KB，并在 stderr 记录 `dropped N by byte cap`

#### 场景:延迟告警
- **当** CLI 在单次调用中检索 + 输出耗时超过 500ms
- **那么** 系统在 stderr 记录告警日志（不影响 stdout 输出）

### 需求:只读调用、无本地副作用

系统必须保证 Hook CLI 在执行过程中不写入任何文件、不发起 API 以外的网络请求、不执行 shell 命令。

#### 场景:无网络时仅后端本地可达
- **当** 主机无外网但 `localhost:3014` 后端正常
- **那么** 系统正常完成注入，不因外网不可达报错

#### 场景:完全离线
- **当** 后端未启动且主机无外网
- **那么** 系统按"后端不可达静默降级"场景处理，不阻塞 OpenCode

## 修改需求
<!-- 无 -->

## 移除需求
<!-- 无 -->
