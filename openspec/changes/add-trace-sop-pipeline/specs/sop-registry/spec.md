## 新增需求

### 需求:SOP 以 Markdown 文件形式持久化

系统必须将每条 SOP 以独立的 Markdown 文件保存于 `backend/data/sops/<user>/<id>.md`。文件首部使用 YAML frontmatter 记录元数据字段：`id`（UUID）、`name`、`version`（整数，初始 1）、`enabled`（布尔）、`tags`（字符串数组）、`created`（ISO8601 日期时间）、`updated`（ISO8601）、`source_trace_ids`（字符串数组）、`confidence`（0–1 浮点数）、`needs_review`（布尔）、`conflict_with`（字符串数组，缺省空）。frontmatter 之后为人类可读的 SOP 正文，包含意图段落和有序步骤列表。

#### 场景:写入新 SOP
- **当** registry 收到一条合法 SOP 候选
- **那么** 系统在 `backend/data/sops/<user>/` 目录（不存在时自动创建）下创建 `<id>.md` 文件，包含完整 frontmatter 与正文，`version=1`、`created`与`updated`相同

#### 场景:frontmatter 字段缺失
- **当** 待写入的 SOP 候选缺少任何一个必填 frontmatter 字段
- **那么** 系统拒绝写入并返回校验错误，不创建文件

#### 场景:写入必须原子
- **当** registry 执行写入操作
- **那么** 系统必须先写入临时文件再通过 `os.replace` 原子替换目标文件，禁止出现半写状态

### 需求:按 user 硬隔离

系统必须按 `user_id`（OS 用户名）对 SOP 做目录级隔离。任何读、写、列举、检索操作必须携带 `user_id`，禁止跨目录访问。路径拼接后必须对实际解析路径做校验，确保不跳出 `backend/data/sops/<user>/` 子树；越界尝试必须抛出 `PermissionError`。

#### 场景:合法访问
- **当** 使用 `user_id="alice"` 调用 registry 的列举接口
- **那么** 系统只返回 `backend/data/sops/alice/` 目录下的 SOP 文件，绝不返回其他目录的任何文件

#### 场景:路径穿越尝试
- **当** 传入形如 `user_id="../bob"` 的参数试图跨用户访问
- **那么** 系统检测到解析后路径跳出合法根目录，抛出 `PermissionError`，不返回任何数据

### 需求:去重与冲突标记

系统必须在写入新 SOP 时做去重检查：若待写入 SOP 的"有序步骤动作名列表"与已有某条 `enabled=true` 的 SOP 完全相同，则合并为同一 SOP 的新版本（`version+=1`、`updated` 刷新、`source_trace_ids` 合并），不创建新文件；若步骤序列与已有 SOP 存在互斥语义（例如一条主张"`git_push`"另一条主张"`create_mr`"），系统必须在双方 frontmatter 的 `conflict_with` 中互相填入对方 id 并将双方 `needs_review` 置为 true。

#### 场景:完全重复的 SOP
- **当** 待写入 SOP 与某条已启用 SOP 的步骤动作名序列完全一致
- **那么** 系统不新建文件，而是更新既有文件的 `version`、`updated`、`source_trace_ids`（并集），保留原 `id`

#### 场景:互斥 SOP
- **当** 待写入 SOP 包含 `git_push` 动作，已有一条同用户、相近 tags 的 SOP 在相近位置包含 `create_mr` 动作
- **那么** 系统允许两者并存，但在双方 frontmatter 互相填入 `conflict_with` 并设 `needs_review=true`

### 需求:提供读/列举/检索接口

系统必须暴露三个稳定函数契约（供 `sop-api` 和 extractor 消费）：
- `list(user_id) -> List[SOPMeta]`：列出该用户下全部 SOP 元信息，按 `updated` 倒序；不读正文。
- `get(user_id, sop_id) -> SOP`：返回完整 SOP 内容；含路径校验。
- `retrieve(user_id, query, k, filters=None, include_disabled=False) -> List[SOP]`：按可选 `query` 文本与 tags 过滤返回 top-K SOP；默认排除 `enabled=false` 与 `needs_review=true`。

后续若替换底层存储（例如切到 Mem0 / 向量库），这三个函数签名必须保持不变。

#### 场景:列出当前用户 SOP
- **当** 调用 `list("alice")`
- **那么** 系统返回 `backend/data/sops/alice/` 下所有 SOP 的元信息列表（不含正文），按 `updated` 倒序

#### 场景:检索时过滤未启用条目
- **当** 调用 `retrieve` 且 `include_disabled=False`（默认）
- **那么** 系统禁止返回 `enabled=false` 或 `needs_review=true` 的 SOP

#### 场景:检索 query 缺省
- **当** 调用 `retrieve` 且不传 `query`
- **那么** 系统按 `updated` 倒序返回前 `k` 条启用 SOP

#### 场景:检索 top-K 截断
- **当** 匹配到 10 条候选但 `k=3`
- **那么** 系统按相关度排序后仅返回前 3 条

#### 场景:目录不存在返回空
- **当** 调用 `list("newuser")` 但 `backend/data/sops/newuser/` 目录尚未创建
- **那么** 系统返回空列表，不抛错

## 修改需求
<!-- 无 -->

## 移除需求
<!-- 无 -->
