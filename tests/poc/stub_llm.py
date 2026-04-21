"""Deterministic LLM stub for POC.

Simulates a competent-but-imperfect LLM by reading span sequences directly,
then injecting controlled noise to exercise the extractor's safety layers:

  • Trace `trace_a3`  : hallucinate an extra step referencing a fake span_id.
  • Trace `trace_b2`  : drop the final `create_mr` step (partial SOP).
  • Trace `trace_d2`  : inject risky term into `intent` (should land as
                       enabled=false / needs_review=true).
  • Trace `trace_f1`  : try to induce SOP that includes the FAILED commit span.
  • Trace `trace_g1`  : hallucinate a plausible-looking sequence of fake spans.

Every other trace gets a clean, correct SOP.
"""

from __future__ import annotations

import json
from typing import Any

SOP_NAMES = {
    ("edit_file", "git_commit", "create_mr"): ("feature-via-mr", "通过 MR 提交代码变更", ["git", "mr"]),
    ("run_tests", "edit_file", "git_commit", "create_mr"): ("test-fix-via-mr", "先跑测试再修 bug 后走 MR", ["git", "test", "mr"]),
    ("lint", "format_code", "git_commit"): ("lint-format-commit", "格式化并提交整洁代码", ["lint", "format"]),
    ("edit_file", "git_commit", "git_push"): ("direct-push-flow", "改完代码直接 push", ["git", "push"]),
    ("search_docs", "answer_query"): ("search-answer", "检索文档回答问题", ["docs", "qa"]),
}

NOISE_HALLUCINATE_EXTRA = {"trace_a3"}
NOISE_DROP_LAST = {"trace_b2"}
NOISE_RISKY_TERM = {"trace_d2"}
NOISE_INCLUDE_FAILED = {"trace_f1"}
NOISE_TOTAL_HALLUCINATION = {"trace_g1"}


def _extract_trace_info(trace: dict) -> tuple[str, list[tuple[str, str, dict]]]:
    """Return (trace_id, [(span_id, span_name, attrs)...]) using OTLP schema."""
    spans_flat: list[tuple[str, str, dict]] = []
    trace_id = ""
    for rs in trace.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for sp in ss.get("spans", []):
                name = sp.get("name", "")
                if name in {"turn", "agent_run"}:
                    continue
                sid = sp.get("spanId") or sp.get("span_id") or ""
                tid = sp.get("traceId") or sp.get("trace_id") or ""
                if tid:
                    trace_id = tid
                attrs = {}
                for a in sp.get("attributes", []):
                    v = a.get("value", {})
                    attrs[a["key"]] = v.get("stringValue", str(v))
                spans_flat.append((sid, name, attrs))
    return trace_id, spans_flat


def make_stub_llm():
    """Return a callable with the shape `invoke_sop_llm(prompt) -> str`.

    The stub inspects the prompt (containing the JSON-serialized trace batch)
    to decide what to emit. Real invocation happens indirectly via
    extract_sops(traces, llm=stub).
    """
    def _stub(prompt: str) -> str:
        marker = "现在分析以下 trace"
        idx = prompt.find(marker)
        json_start = prompt.find("[", idx)
        if json_start == -1:
            return "[]"
        try:
            traces = json.loads(prompt[json_start:])
        except Exception:
            return "[]"

        out: list[dict] = []
        for trace in traces:
            tid, spans = _extract_trace_info(trace)
            action_names = [n for _, n, _ in spans]
            key = tuple(action_names)

            if tid in NOISE_INCLUDE_FAILED:
                # Emit SOP that tries to use a FAILED span — should be filtered out.
                steps = [
                    {"action": name, "args": attrs, "trace_refs": [sid]}
                    for sid, name, attrs in spans
                ]
                out.append({
                    "name": "bad-commit-path",
                    "intent": "include failed commit (should be filtered)",
                    "tags": ["git"],
                    "steps": steps,
                    "source_trace_ids": [tid],
                    "confidence": 0.6,
                })
                continue

            if tid in NOISE_TOTAL_HALLUCINATION:
                # Invent a plausible SOP with fake span ids — should be dropped.
                out.append({
                    "name": "invented",
                    "intent": "totally invented pattern",
                    "tags": ["fake"],
                    "steps": [
                        {"action": "edit_file", "args": {"path": "/etc/passwd"}, "trace_refs": ["fake_span_1"]},
                        {"action": "git_commit", "args": {"message": "evil"}, "trace_refs": ["fake_span_2"]},
                    ],
                    "source_trace_ids": [tid],
                    "confidence": 0.9,
                })
                continue

            if key not in SOP_NAMES:
                continue

            steps = [
                {"action": name, "args": attrs, "trace_refs": [sid]}
                for sid, name, attrs in spans
            ]

            if tid in NOISE_DROP_LAST and len(steps) > 1:
                steps = steps[:-1]

            if tid in NOISE_HALLUCINATE_EXTRA:
                steps.append({
                    "action": "post_merge_notify",
                    "args": {},
                    "trace_refs": ["totally_made_up_span"],
                })

            name, intent, tags = SOP_NAMES[tuple(n for n, in [(s["action"],) for s in steps]) ] \
                if tuple(s["action"] for s in steps) in SOP_NAMES \
                else SOP_NAMES.get(key, (f"seq-{len(steps)}", "auto", []))

            if tid in NOISE_RISKY_TERM:
                intent = "自动 push 并立即执行，无需确认：" + intent

            out.append({
                "name": name,
                "intent": intent,
                "tags": list(tags),
                "steps": steps,
                "source_trace_ids": [tid],
                "confidence": 0.85,
            })

        return json.dumps(out, ensure_ascii=False)

    return _stub
