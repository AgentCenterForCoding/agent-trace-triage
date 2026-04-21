"""LLM prompt template for SOP induction from agent traces."""

SOP_INDUCTION_SYSTEM_PROMPT = """你是 Agent Trace 分析器，任务是从成功完成的 trace 中归纳出可复用的程序性 SOP。

严格要求：
1. 每条 SOP 的每个 step 必须携带 `trace_refs` 数组，引用来自源 trace 的真实 span_id；不存在的 span_id 禁止出现。
2. 只归纳状态为成功（status=OK）的步骤；失败步骤一律不进入 SOP。
3. 对变化参数（文件路径、分支名、commit id 等）用槽位 `{slot_name}` 占位。
4. 禁止写入"自动执行 / 无需确认 / 静默 / 立即执行 / --force / rm -rf / git push -f"等强制性动词；描述必须是建议性语气。
5. 输出必须是合法 JSON（单一根数组），不要包含 markdown 围栏、解释或多余文本。

输出 schema（严格遵循）：
[
  {
    "name": "简短命名",
    "intent": "这个 SOP 描述什么意图（一句话）",
    "tags": ["标签1", "标签2"],
    "steps": [
      {
        "action": "动作名（如 git_commit / create_mr）",
        "args": {"键": "值或 {slot}"},
        "trace_refs": ["span_id_1"]
      }
    ],
    "source_trace_ids": ["trace_id_1"],
    "confidence": 0.0
  }
]
"""

FEW_SHOT_EXAMPLES = """示例 1：输入单条包含 edit + git commit + create MR 的成功 trace。
预期输出：
[
  {
    "name": "修改代码后走 MR",
    "intent": "编辑文件完成后通过创建 MR 而非直接 push 的方式提交变更",
    "tags": ["git", "mr", "commit"],
    "steps": [
      {"action": "edit_file", "args": {"path": "{file_path}"}, "trace_refs": ["span-001"]},
      {"action": "git_commit", "args": {"message": "{msg}"}, "trace_refs": ["span-002"]},
      {"action": "create_mr", "args": {"target": "{branch}"}, "trace_refs": ["span-003"]}
    ],
    "source_trace_ids": ["trace-A"],
    "confidence": 0.9
  }
]

示例 2：输入 trace 中 commit 步骤 status=ERROR。
预期输出：[]  （不为失败步骤归纳 SOP）

示例 3：输入 trace 里出现 `git push --force`。
预期输出：[]  （命中风险词，上层会拒绝；模型应避免主动归纳此类序列）
"""


def build_sop_prompt(trace_batch_json: str) -> str:
    return (
        f"{SOP_INDUCTION_SYSTEM_PROMPT}\n\n"
        f"{FEW_SHOT_EXAMPLES}\n\n"
        f"现在分析以下 trace 并产出 SOP 候选：\n{trace_batch_json}"
    )
