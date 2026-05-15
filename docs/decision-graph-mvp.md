---
feature_ids: [decision-graph]
topics: [trace, visualization, mvp, agent-behavior-graph]
doc_kind: design
created: 2026-05-15
---

# Trace Agent Graph MVP 设计方案

> 版本：v0.1（MVP）
> 日期：2026-05-15
> 关联：`docs/opencode-trace-spec.md`、`docs/trace_analyse.md`、`Trace Agent Graph _standalone_.html`

## 文档结构

九节：目标与非目标、概念映射、架构与数据流、Deviation 检测规则、视觉规范、MVP 范围、实施计划、与画像 Pipeline 的协同、风险与对策。

---

## 一、目标与非目标

### 1.1 目标

把一条 OTLP trace 投影成一张"决策行为图"（Agent Behavior Graph），让用户能在 30 秒内看出：

1. Agent 在哪几个关键节点做了决策
2. 每个决策走了哪条分支
3. 哪条分支偏离了"该走的路"（deviation 红点）
4. 偏离的根因 Span 在哪里

视觉锚定参考：现有 `Trace Agent Graph _standalone_.html` 头部 SVG 缩略图——
方块（User）→ 菱形（Decision）→ 两条方块分支（Tool）→ 圆（Output），其中一条分支带红色 `!` deviation badge。

### 1.2 非目标（Out of Scope）

- ❌ 跨 trace 聚合 / 超级个体画像（已由 `trace_analyse.md` Pipeline 覆盖）
- ❌ 时间轴 / Gantt 视图（互补但不在本 MVP）
- ❌ 实时流式渲染（先做离线静态图）
- ❌ 编辑 / 重放 trace
- ❌ 多 trace 并排对比

### 1.3 与 `trace_analyse.md` 的关系

两者**正交互补**：

| 维度 | `trace_analyse.md` Pipeline | 本 MVP |
|---|---|---|
| 视角 | 跨 trace、跨用户 | 单条 trace |
| 产出 | 五份画像资产（SOP、决策树等） | 一张可视化图 |
| 用途 | 沉淀超级个体能力、复制推广 | 故障归因、行为理解 |
| 共享 | OTLP Parser（阶段 1）、function_name 映射表（阶段 2） | 同上 |

---

## 二、概念映射（OTLP Span → Graph 元素）

### 2.1 节点与边的形状语言

| Graph 元素 | 形状 | OTLP 来源 | 节点语义 |
|---|---|---|---|
| User | 方块 | `turn` + `prompt.id` / `user_message_text` | 入口意图 |
| Agent Frame | 圆角矩形容器 | `agent_run` | 子 graph 分组（main vs sub_agent） |
| **Decision** | **菱形** | `model_inference`（按 `finish_reasons` 分类） | 关键决策点 |
| Tool Action | 方块 | `tool_call` | 执行动作 |
| Approval Gate | 人形小菱形 | `user_approval` | 用户决策点 |
| Output | 圆 | 最后一个 `finish_reasons=stop` 的 `model_inference` | 终态 |
| Edge | 连线 | `parentSpanId` 关系 + 时间序 | 因果/时序 |
| **Deviation Badge** | 红色 ! 角标 | 见 §四 检测规则 | 偏离/异常标记 |

### 2.2 关键投影规则

#### Rule 1：Decision 折叠

连续的 `model_inference → tool_call → tool_result → model_inference` 链，把每个 `model_inference` 提为菱形决策点；其 `finish_reasons` 决定出边类型：

- `finish_reasons=tool_use` → 一条实线边连出到 tool_call
  - MVP：单分支（model 实际选择的那个）
  - Phase 2：从 model 输出原文中解析"曾考虑的 N 个选项"补虚线备选分支
- `finish_reasons=stop` → 终止边，连到 Output 圆
- `finish_reasons=max_tokens` → 异常终止边（红色虚线 + warning badge）
- `finish_reasons=content_filter` → 异常终止边（黄色虚线 + info badge）

#### Rule 2：Sub-agent 嵌套

`agent_run` 嵌套的 `agent_run` 渲染成可折叠子图（默认折叠为单个圆角矩形节点 `[sub_agent: <name>]`，点击展开）。展开后的内部图与主图共享同一画布。

#### Rule 3：Loop 收敛

同一个 `agent_run` 内的 `turn_count` 个内部循环：

- Phase 1：全部展开，纵向重复段
- Phase 2：加 "折叠重复" 按钮，将 N 次相同模式合并为 `[×N loop]` 标签

#### Rule 4：Approval 嵌入

`user_approval` 作为 tool_call 的前置 gate，渲染为一个小菱形挂在对应 tool_call 上方；其 `decision` 决定后续路径着色。

---

## 三、架构与数据流

### 3.1 五段 Pipeline

```
OTLP JSON (单条 trace)
       │
       ▼
┌──────────────────────────────────────┐
│  Stage A: OTLP Parser                │  复用 trace_analyse 阶段 1 的扁平化逻辑
│  → Span Tree (内存模型)              │  （单 trace 模式，不落 Parquet）
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Stage B: Graph Projector            │  ★ MVP 新增的核心模块
│  → Nodes + Edges + Meta              │  按 §二投影规则折叠 Span 树
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Stage C: Deviation Annotator        │  按 §四规则打 deviation 标签
│  → Nodes/Edges + deviation 字段      │  + 上溯根因边
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Stage D: Layout                     │  dagre LR 分层布局
│  → 节点坐标                          │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Stage E: Renderer                   │  React + @xyflow/react
│  → 单文件 HTML                        │  bundler 模式，对齐现有 standalone 产物
└──────────────────────────────────────┘
```

### 3.2 技术栈

| 层 | 选型 | 备注 |
|---|---|---|
| Backend | Python 3.11+ | 复用 `trace_analyse` 已有的 OTLP parser |
| Graph 中间格式 | JSON | 标准 schema，前后端解耦 |
| Frontend 框架 | React 18 | 与现有 `Trace Agent Graph _standalone_.html` 一致 |
| 图渲染 | `@xyflow/react`（原 React Flow） | 原生支持自定义节点形状 + dagre 布局 |
| 打包 | bundler 套路（`__bundler/manifest` + base64 + DecompressionStream） | 照搬现有 standalone HTML 的实现 |
| CLI | `agent-trace-graph render <trace.json> -o graph.html` | 单命令产出 |

### 3.3 标准 Graph JSON Schema

```json
{
  "trace_id": "abc123",
  "meta": {
    "total_duration_ms": 15234,
    "total_tokens": 8500,
    "tool_call_count": 7,
    "deviation_count": 2
  },
  "nodes": [
    {
      "id": "n_<spanId>",
      "type": "user | agent_frame | decision | tool | approval | output",
      "shape": "rect | diamond | circle | rounded_rect | person",
      "label": "...",
      "span_ref": "<spanId>",
      "attrs": { /* 原 Span attributes 透传 */ },
      "deviation": {
        "level": "critical | warning | info | none",
        "reason": "tool_failure | max_tokens | denied | timeout | retry | content_filter | error_status",
        "root_cause_node_id": "n_<spanId>"
      }
    }
  ],
  "edges": [
    {
      "id": "e_<from>_<to>",
      "source": "n_xxx",
      "target": "n_yyy",
      "type": "control | data | root_cause",
      "style": "solid | dashed_red | dashed_yellow | dotted",
      "label": "1.2s"
    }
  ]
}
```

---

## 四、Deviation 检测规则（MVP 版本）

MVP 阶段只做**单 trace 内的硬规则**，不依赖跨 trace 基线（基线由 `trace_analyse` 阶段 5B/5C 后续灌入）。

### 4.1 检测规则表

| 等级 | 触发条件 | 视觉表现 |
|---|---|---|
| 🔴 Critical | `status.code=ERROR` 显式错误 | 节点描红边 + 红 ! 角标 |
| 🔴 Critical | `agent_run.terminate_reason ∈ {error, timeout}` | Frame 描红 |
| 🟠 Warning | `tool_call.success=false` | 节点橙边 + ! 角标 |
| 🟠 Warning | `model_inference.finish_reasons=max_tokens` | Decision 菱形橙边 + 出边虚线 |
| 🟠 Warning | `user_approval.decision=denied` | Approval 节点橙边 |
| 🟡 Info | `user_approval.decision=timeout` | Approval 节点黄边 |
| 🟡 Info | 同一 tool_call 上游出现 ≥3 次 model_inference 重试 | Decision 黄角标 + 重试计数 |
| 🟡 Info | `model_inference.finish_reasons=content_filter` | Decision 黄边 |

### 4.2 根因传播

在 Critical/Warning 节点上额外计算 **upstream root cause**——按 `opencode-trace-spec.md §5.2` 的规则上溯：

| 场景 | 根因归属 |
|---|---|
| Model 输出坏参数 → tool_call 失败 | 根因 = 上游 model_inference |
| User 长时间不响应 → timeout | 根因 = user_interaction（非系统故障） |
| User 拒绝 → 流程中断 | 根因 = user_approval |

在前端用一条**虚线箭头**（`type=root_cause`）从故障节点指回根因节点。

### 4.3 故障语义来自 spec，不重复造轮子

本节规则严格对齐 `opencode-trace-spec.md §5`，未来 spec 演进时只需同步本节规则表。

---

## 五、视觉规范

### 5.1 配色（对齐现有 SVG 缩略图）

直接沿用目标 HTML 的 oklch 配色，保证视觉一致性：

| 元素 | 形状 | 颜色 | 备注 |
|---|---|---|---|
| User | 方块 | `oklch(32% 0.02 80)` 描边 | 灰墨色 |
| Decision (model_inference) | 菱形 | `oklch(54% 0.15 70)` 描边 | 琥珀色 |
| Tool (skill) | 方块 | `oklch(48% 0.13 155)` 描边 | 青绿 |
| Tool (mcp) | 方块 | 蓝色系 oklch(48% 0.13 240) | 区分 tool_type |
| Tool (builtin) | 方块 | 灰绿 oklch(48% 0.06 155) | |
| Output | 圆 | `oklch(48% 0.17 145)` 描边 | 深绿 |
| Approval | 人形菱形 | 紫色 oklch(48% 0.13 290) | |
| Deviation Badge | 圆 + ! | `oklch(52% 0.22 25)` 红 | 节点右上角 |

### 5.2 布局

- dagre LR（左→右）方向
- 分层：Span depth
- 同层内：按 startTime 排序
- 子 Agent 折叠时占一个节点位；展开时撑开成子区域

### 5.3 交互（MVP 限定）

| 交互 | 行为 |
|---|---|
| 点击节点 | 右侧 Drawer 展示该 Span 的全部 attributes + raw JSON |
| Hover 边 | tooltip 显示耗时 |
| 顶部 Filter | 按 deviation 等级、tool_type、agent_name 高亮/隐藏 |
| 顶部 Metric 条 | 总耗时、token、tool_call 数、deviation 计数 |
| 点击 deviation badge | 自动滚动到 root_cause 节点并高亮根因边 |
| 点击 sub_agent 折叠节点 | 展开/收起子图 |

### 5.4 图例（Legend）

固定在画布右下角的小图例区，列出所有 7 类节点 + 4 种边样式。

---

## 六、MVP IN / OUT

### 6.1 MVP IN（约 2 周）

1. Backend Stage A-C：单 trace OTLP → Graph JSON
2. Frontend：React + @xyflow/react，5 类节点 + 3 类 deviation 渲染
3. 单文件 HTML 打包（bundler 套路）
4. 一个 CLI：`agent-trace-graph render <trace.json> -o graph.html`
5. 5 条 demo trace 覆盖典型场景（成功、tool 失败、user denied、max_tokens、sub_agent 嵌套）

### 6.2 MVP OUT（明确 Phase 2+）

- 备选分支可视化（model 没选的 tool）：OTLP 不带，需要从 model 输出原文中解析"曾考虑的 N 个选项"
- 跨 trace 基线 deviation：依赖 `trace_analyse` 阶段 5B 的 SOP 频繁序列产出
- 时间轴并排视图
- 在线服务化（多用户 trace 浏览）
- Loop 折叠的 `[×N]` 收敛
- 多 trace 对比 / 差异高亮

---

## 七、实施计划（2 周 MVP）

| 周 | 日 | 任务 | 产出 |
|---|---|---|---|
| W1 | D1-2 | 复用 `trace_analyse` OTLP parser，包成单 trace 模式 | `parser.py` |
| W1 | D3-4 | 实现 Graph Projector（§二投影规则） | `projector.py` + 单测 |
| W1 | D5 | 实现 Deviation Annotator（§四规则） | `annotator.py` + 单测 |
| W1 | D5（并行） | Spike：@xyflow/react + bundler 兼容性验证 | spike 报告 |
| W2 | D1-2 | React + @xyflow/react 节点/边样式 | 5 类 node + 3 类 edge |
| W2 | D3 | dagre 布局接入 + Drawer | 完整页面 |
| W2 | D4 | bundler 打包脚本 | `bundle.py` |
| W2 | D5 | 5 条 demo + README | 可演示 |

### 7.1 验收标准

把现有 `Trace Agent Graph _standalone_.html` SVG 缩略图所示场景（User → Decision → 两条 Tool 分支 → 一条带 deviation badge），用真实 OTLP trace 跑出**视觉一致**的效果。

### 7.2 资源需求

- 1 名前后端通吃工程师，2 周
- 不需要额外 LLM API 预算（MVP 不调 LLM）
- 不需要额外存储（单 trace、内存处理）

---

## 八、与 `trace_analyse.md` Pipeline 的协同

两者**共享 Stage A**（OTLP parser）。后续可以反向打通：

| 协同方向 | 描述 |
|---|---|
| `trace_analyse` → 本 MVP | 阶段 5B（PrefixSpan SOP）的频繁序列 → 注入本图作为"典型路径基线"，让 deviation 从"硬规则"升级为"路径偏差" |
| `trace_analyse` → 本 MVP | 阶段 5C（决策点识别）的决策分类 → 反向标注本图的菱形节点（启用 sub_agent / approval 后修正等） |
| 本 MVP → `trace_analyse` | 本图的 Graph JSON → 反过来作为 `trace_analyse` 阶段 4 LLM 标注的输入（结构化比扁平表更利于 LLM 理解） |
| 本 MVP → `trace_analyse` | 本图的 deviation 标签 → 反向供给 `trace_analyse` 的反模式挖掘（阶段 5B Step 4） |

---

## 九、风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `@xyflow/react` 用 ESM，bundler 套路是否兼容未知 | 阻塞 W2 | W1 末做 spike：先把 @xyflow/react Hello World 走完 bundler 流程 |
| 大 trace（1000+ Span）布局卡顿 | 用户体验 | dagre 异步 worker；Span > 200 时默认折叠 sub_agent |
| OpenAgent trace 的 `tool_type` 退化为 `native`（已知） | 节点配色无法区分 skill/mcp/builtin | 复用 `trace_analyse` 阶段 2 的 function_name → tool_type 映射表 |
| OTLP JSON 字段缺失（如老版本无 `finish_reasons`） | Projector 报错 | Projector 加 fallback：缺 `finish_reasons` 时按 child 数推断 |
| Deviation 规则与未来 spec 演进脱节 | 长期维护成本 | §四规则严格对齐 `opencode-trace-spec.md §5`，spec 演进时同步本节 |
| 单文件 HTML 体积过大（@xyflow/react 体积 ~200KB） | 邮件分发不便 | 接受现状；体积红线设 1MB，超出再考虑外链资源模式 |

---

## 附录

### A. 关联文档

- `docs/opencode-trace-spec.md` — OTLP Span 规范（数据源契约）
- `docs/trace_analyse.md` — 跨 trace 画像 Pipeline（互补能力）
- `Trace Agent Graph _standalone_.html` — 视觉锚定参考（SVG 缩略图所示形状语言）

### B. 关键术语

| 术语 | 定义 |
|---|---|
| 决策行为图 | 把 Span 树折叠成"User → Decision → Tool → Output"决策分支图的可视化 |
| Decision 节点 | OTLP `model_inference` Span 在图中的菱形投影 |
| Deviation Badge | 节点右上角的红/橙/黄角标，标注异常等级 |
| Root Cause Edge | 故障节点指回根因节点的虚线箭头 |
| 折叠 sub_agent | 把嵌套 `agent_run` 默认收起为单节点的渲染策略 |

### C. 后续设计议题

1. 备选分支可视化的数据来源（model 输出原文的解析 spec）
2. 跨 trace 基线 deviation 的契约（`trace_analyse` 阶段 5B 输出格式）
3. 时间轴 + 决策图双视图联动方案
4. 服务化部署模式（如何承载多用户 trace 浏览）
