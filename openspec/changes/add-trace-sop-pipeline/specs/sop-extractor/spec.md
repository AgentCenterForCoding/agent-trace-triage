## 新增需求

### 需求:从已解析 Trace 中归纳程序性 SOP

系统必须提供一个批处理能力，输入一组已由 `trace-parser` 解析过的 trace（JSON/结构化形式），输出零条或多条槽位化的 SOP 候选。每条 SOP 必须包含：名称、意图描述、有序步骤列表、适用条件（tags）、源 trace 引用列表、归纳置信度（0–1 浮点数）。

#### 场景:从单条成功 trace 归纳 SOP
- **当** 输入一条包含"文件修改 → `git commit` → 创建 MR"三个成功动作的 trace
- **那么** 系统产出一条至少包含这三步的 SOP 候选，步骤顺序与 trace 中的发生顺序一致

#### 场景:从多条同类 trace 归纳通用模板
- **当** 输入 3 条流程一致但具体参数不同的 trace（例如都走"edit → commit → MR"，但分支名/文件路径不同）
- **那么** 系统归纳出一条 SOP，变化的参数以槽位（形如 `{branch_name}`、`{file_path}`）占位

#### 场景:对不成功 trace 不归纳执行类步骤
- **当** 输入的 trace 中某步骤以失败状态结束（status != OK）
- **那么** 系统禁止将该失败步骤作为 SOP 的必备步骤；若整条 trace 无成功可复用序列，则产出零条 SOP

### 需求:每步必须携带源 Trace 引用

系统必须在每个 SOP 步骤中保留至少一个对源 trace 的引用（`span_id`）。无引用或引用在源 trace 中不存在的步骤必须被视为幻觉并丢弃。

#### 场景:校验引用存在
- **当** LLM 归纳输出中某步骤的 `trace_refs` 列表为空或引用的 `span_id` 不在输入 trace 中
- **那么** 系统丢弃该步骤所在的整条 SOP 候选，并在归纳摘要里累计 `dropped_hallucination`

#### 场景:允许一步引用多条 trace
- **当** 多条输入 trace 中都存在相同语义的步骤
- **那么** 系统允许该步骤的 `trace_refs` 同时包含多个 `span_id`，分别来自不同源 trace

### 需求:安全词汇静态扫描

系统必须在入库前对 SOP 正文做静态词汇扫描，命中预定义风险名单（包含但不限于"自动执行""无需确认""静默""立即执行""`--force`""`rm -rf`""`git push -f`"）的 SOP 必须被标记为 `needs_review` 且默认 `enabled: false`。

#### 场景:命中风险词
- **当** LLM 归纳出的 SOP 步骤文本包含"自动 `git push -f`"字样
- **那么** 系统将该 SOP 的 `enabled` 置为 `false`、添加 `needs_review` 标签，并在归纳摘要里累计 `dropped_risky` 或 `flagged_risky`

#### 场景:未命中风险词
- **当** SOP 全部步骤文本均为"建议/可考虑/推荐"语气且不含名单词
- **那么** 系统允许 SOP 以 `enabled: true` 入库（仍需经 registry 的去重检查）

### 需求:可通过命令行调用

系统必须提供一个命令行入口 `python -m backend.sop.extractor`，接受 `--traces <dir>`、`--out <dir>`、`--user <id>` 三个参数；`--user` 缺省时必须回落到 `os.getlogin()`。退出码 0 表示成功，非 0 表示失败。

#### 场景:正常批处理
- **当** 使用合法参数调用 extractor CLI
- **那么** 系统扫描输入目录下所有 trace、归纳出 SOP 候选、通过 registry 写入、以退出码 0 结束，并在 stdout 输出 JSON 摘要 `{"produced": N, "dropped_hallucination": N, "dropped_risky": N, "total": N}`

#### 场景:参数非法
- **当** `--traces` 指向的目录不存在，或 `--user` 为空且 `os.getlogin()` 抛错
- **那么** 系统以非 0 退出码结束并在 stderr 输出错误说明，不产生任何 SOP 文件，stdout 不输出 JSON 摘要

## 修改需求
<!-- 无 -->

## 移除需求
<!-- 无 -->
