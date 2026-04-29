# 默认任务 Taxonomy + tool_type 映射建库

## 一、默认 15 类任务 taxonomy

设计原则：**宁可粗也别一开始就太细**。15-20 类是经验上的甜区——再粗会丢信息，再细会让 LLM 标注准确率掉到 70% 以下。

每个 task_type 包含：ID、名称、判断要点、典型 user_message_text 样例。

```yaml
- id: REQ_ANALYSIS
  name: 需求分析
  judging_hint: 用户在描述模糊或不完整的需求，要求拆解成可执行项
  examples:
    - "我们想做一个 ... 你帮我看下要从哪些维度考虑？"
    - "PM 提了个需求 ..., 帮我拆一下 acceptance criteria"
    - "对这个 feature 你有什么补充问题？"

- id: SOLUTION_DESIGN
  name: 方案设计
  judging_hint: 已有明确目标，要求给出实现方案/架构/方法论
  examples:
    - "想实现 X 功能，给我 2-3 个方案 + 取舍"
    - "这块用 Redis 还是 Kafka 比较合适？"
    - "数据流应该怎么设计？"

- id: CODE_WRITING
  name: 代码编写
  judging_hint: 直接要求生成具体代码片段或函数
  examples:
    - "帮我写一个 Python 函数 ..."
    - "给我一段 SQL 查询 ..."
    - "实现 XX 接口"

- id: CODE_REVIEW
  name: 代码评审
  judging_hint: 用户提供已有代码，要求评审/优化
  examples:
    - "看下这段代码有没有问题"
    - "review 我这个 PR"
    - "这块写得怎么样，能优化吗"

- id: CODE_REFACTOR
  name: 代码重构
  judging_hint: 已有代码可工作但要求结构优化
  examples:
    - "把这段重构一下，提取成 ..."
    - "这个函数太长了，帮我拆"
    - "去掉重复逻辑"

- id: BUG_FIX
  name: bug 修复
  judging_hint: 描述错误现象/堆栈，要求定位和修复
  examples:
    - "报这个错怎么解 ..."
    - "为什么这段代码不工作"
    - "测试挂了，帮我看下"

- id: DATA_ANALYSIS
  name: 数据分析
  judging_hint: 给定数据文件/表，要求统计/可视化/洞察
  examples:
    - "看下这份 CSV，统计 X 维度的分布"
    - "为什么这个指标这周下跌了"
    - "做个 dashboard 显示 ..."

- id: DOC_WRITING
  name: 文档撰写
  judging_hint: 要求生成文档、说明、规范
  examples:
    - "写一份 API 文档"
    - "给这个模块写个 README"
    - "整理成一份 design doc"

- id: COMPETITIVE_RESEARCH
  name: 竞品/技术调研
  judging_hint: 调研外部技术/产品/框架
  examples:
    - "调研一下 X 框架的现状"
    - "对比 A B C 三个方案"
    - "看下 OpenAI 最近的更新"

- id: TEST_WRITING
  name: 测试编写
  judging_hint: 要求生成测试用例、单测、e2e
  examples:
    - "给这个函数写单测"
    - "补一下 edge case 测试"
    - "把这个流程写成 e2e"

- id: DEVOPS_OPS
  name: DevOps/运维操作
  judging_hint: 涉及部署、CI/CD、监控、容器配置
  examples:
    - "这个 Dockerfile 怎么改"
    - "K8s 部署配置 ..."
    - "GitHub Actions workflow ..."

- id: CONFIG_SETUP
  name: 配置/环境搭建
  judging_hint: 安装依赖、配置工具、初始化项目
  examples:
    - "怎么装 X"
    - "配置 ... 的步骤"
    - "初始化一个 Vite + React 项目"

- id: KNOWLEDGE_QUERY
  name: 知识查询
  judging_hint: 概念解释、用法查询、原理问答
  examples:
    - "什么是 SSE？"
    - "Pandas 这个用法怎么写"
    - "解释一下 RAFT 算法"

- id: META_TASK
  name: AI 工作流元任务
  judging_hint: 涉及 prompt 优化、skill 设计、agent 配置
  examples:
    - "优化下这个 prompt"
    - "给我设计一个 X 的 skill"
    - "agent 配置怎么写"

- id: OTHER
  name: 其他
  judging_hint: 无法归入上述任意一类，或跨多类
  examples:
    - 杂项 / 闲聊 / 不明确意图
```

**使用时**：

1. 把这 15 类作为 taxonomy 起点。
2. **先在 50 条 Gold Set 上跑分类，看是否有明显聚集到 OTHER**——如果 OTHER > 15%，说明 taxonomy 缺类，要新增。
3. 不要一开始就拆 30 类。先粗后细。每月评估一次，按 OTHER 占比决定是否细化。

## 二、function_name → tool_type 映射建库流程

`tool_type_mapping.json` 是 Step 2 的关键基础设施。从 0 到 95% 覆盖率的标准流程：

### Step 1：抽样统计

```python
# 在数据接入完成后立即跑
import pandas as pd
tools = pd.read_parquet("tool_call_table.parquet")
freq = tools["function_name"].value_counts().reset_index()
freq.columns = ["function_name", "count"]
freq.to_csv("function_name_frequencies.csv", index=False)
```

要求：覆盖最近 1000+ 条 trace，确保覆盖大多数 function_name。

### Step 2：人工分类（首轮）

打开 `function_name_frequencies.csv`，按出现频次降序，对前 N 个（覆盖到 95% 累计频率即可）人工标注：

| function_name | count | derived_tool_type | tool_subtype | notes |
|---|---|---|---|---|
| skill | 1240 | skill | (从 input 解析) | 通用入口 |
| bash | 980 | builtin | | |
| read_file | 870 | builtin | | |
| edit_file | 720 | builtin | | |
| grep_search | 530 | builtin | | |
| mcp__playwright__browser_navigate | 280 | mcp | playwright/browser_navigate | |
| mcp__filesystem__read_file | 180 | mcp | filesystem/read_file | |
| ... | | | | |

判定规则：

- 包含 `mcp__` 前缀 → mcp，subtype 取 `__` 之间的部分
- 是 `skill` / `Skill` / 类似入口 → skill，subtype 从 tool_input_text 解析
- 文件操作、shell、grep、glob、ls 等 → builtin
- 不确定的 → 写入 unknown 队列，先标 `unknown` 不要瞎猜

### Step 3：写成 mapping JSON

```json
{
  "version": "1.0",
  "updated_at": "2026-04-29",
  "function_name_to_type": {
    "skill": {
      "tool_type": "skill",
      "subtype_extractor": "json_field:skill"
    },
    "bash": {"tool_type": "builtin"},
    "read_file": {"tool_type": "builtin"},
    "mcp__playwright__browser_navigate": {
      "tool_type": "mcp",
      "subtype": "playwright/browser_navigate"
    }
  },
  "patterns": [
    {
      "pattern": "^mcp__([^_]+)__(.+)$",
      "tool_type": "mcp",
      "subtype_template": "{1}/{2}"
    }
  ]
}
```

支持两种命中：
- 精确 function_name 命中（高优先级）
- 正则 pattern 命中（兜底）

### Step 4：周度审核

```python
# 每周跑一次
unknowns = tools[tools["derived_tool_type"] == "unknown"]["function_name"].unique()
print(f"待审核新出现 function_name: {len(unknowns)}")
unknowns.tolist()  # 导出给人工分类，更新 mapping
```

### Step 5：subtype 解析（针对 skill）

`tool_input_text` 在 OpenAgent 下的常见结构：

```
{"skill": "agent-trace-triage", "args": {...}}
{"skill_name": "tech-evaluation", ...}
"--skill agent-trace-triage --args ..."
```

解析逻辑：

```python
import json, re

def extract_skill_subtype(tool_input_text: str) -> str | None:
    if not tool_input_text:
        return None
    # try JSON
    try:
        obj = json.loads(tool_input_text)
        for key in ("skill", "skill_name", "name"):
            if isinstance(obj, dict) and key in obj:
                return obj[key]
    except json.JSONDecodeError:
        pass
    # try CLI-like
    m = re.search(r"--skill[= ]([\w\-]+)", tool_input_text)
    if m:
        return m.group(1)
    return None
```

### Step 6：覆盖率门槛

每次 Pipeline 运行前自检：

- **mapping 命中率 ≥ 95%**：unknown 比例 < 5%
- **subtype 解析成功率 ≥ 85%**（针对 derived_tool_type=skill 的行）

不达标时：
- 95% 以下 → 拒绝运行，先补 mapping
- 95-95% → 允许运行，但所有"工具偏好"产物加 caveat

## 三、Taxonomy 与映射的演进

| 时间 | 动作 |
|---|---|
| Pipeline 第 1 次跑前 | 用本文件的默认 15 类 + 抽样建 mapping |
| 每次跑完 | 统计 OTHER 占比 + unknown 队列长度 |
| 每月 | 评估是否新增 task_type；批量审核 unknown 队列 |
| 每季度 | 重大调整 taxonomy（合并/拆分），重新跑历史数据回填 |
