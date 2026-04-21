"""Generate 20 POC traces in OTLP JSON format (mirrors sample_traces/ style)
for SOP-induction evaluation.

Coverage design:
- 6  × Pattern A  (edit → git_commit → create_mr)            — slotify/dedup stress
- 4  × Pattern B  (run_tests → edit → git_commit → create_mr)
- 3  × Pattern C  (lint → format_code → git_commit)
- 3  × Pattern D  (edit → git_commit → git_push)             — conflicts with A
- 2  × Pattern E  (search_docs → answer_query)               — non-git workflow
- 1  × Pattern F  (edit → git_commit FAILED)                 — failed-step filter
- 1  × Pattern G  (many noisy spans, no coherent SOP)        — hallucination bait
"""

import json
from pathlib import Path
from typing import Any

POC_DIR = Path(__file__).parent / "traces"
POC_DIR.mkdir(exist_ok=True)


def _span(trace_id, span_id, name, *, parent=None, status="OK", t0=0, dur=1_000_000_000, attrs=None):
    status_dict = {"code": status, "message": f"{name} {status}"}
    span = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": name,
        "startTimeUnixNano": str(1_700_000_000_000_000_000 + t0),
        "endTimeUnixNano": str(1_700_000_000_000_000_000 + t0 + dur),
        "status": status_dict,
        "attributes": [{"key": k, "value": {"stringValue": str(v)}} for k, v in (attrs or {}).items()],
    }
    if parent:
        span["parentSpanId"] = parent
    return span


def _build(trace_id, spans):
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def _write(filename, doc):
    (POC_DIR / filename).write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Pattern A: edit → git_commit → create_mr ────────────────────────
A_FIXTURES = [
    ("poc_a1.json", "trace_a1", "src/auth.py",    "feat/auth-refactor",     "refactor auth"),
    ("poc_a2.json", "trace_a2", "src/api.py",     "fix/api-headers",        "fix auth headers"),
    ("poc_a3.json", "trace_a3", "README.md",      "docs/quickstart",        "update quickstart"),
    ("poc_a4.json", "trace_a4", "backend/db.py",  "feat/pool-tuning",       "tune conn pool"),
    ("poc_a5.json", "trace_a5", "ui/App.tsx",     "fix/ui-layout",          "fix layout jitter"),
    ("poc_a6.json", "trace_a6", "tests/x.py",     "test/smoke-case",        "add smoke test"),
]
for fname, tid, path, branch, msg in A_FIXTURES:
    _write(fname, _build(tid, [
        _span(tid, f"{tid}_root", "turn",          t0=0,          dur=5_000_000_000),
        _span(tid, f"{tid}_agent","agent_run",     parent=f"{tid}_root", t0=100_000_000,  dur=4_800_000_000),
        _span(tid, f"{tid}_s1",   "edit_file",     parent=f"{tid}_agent", t0=200_000_000, dur=600_000_000, attrs={"path": path}),
        _span(tid, f"{tid}_s2",   "git_commit",    parent=f"{tid}_agent", t0=900_000_000, dur=400_000_000, attrs={"message": msg}),
        _span(tid, f"{tid}_s3",   "create_mr",     parent=f"{tid}_agent", t0=1_400_000_000, dur=600_000_000, attrs={"target": branch}),
    ]))

# ── Pattern B: run_tests → edit → git_commit → create_mr ────────────
B_FIXTURES = [
    ("poc_b1.json", "trace_b1", "tests/login",      "src/login.py",  "fix login null"),
    ("poc_b2.json", "trace_b2", "tests/billing",    "src/billing.py","fix rounding"),
    ("poc_b3.json", "trace_b3", "tests/search",     "src/search.py", "fix empty query"),
    ("poc_b4.json", "trace_b4", "tests/export",     "src/export.py", "escape commas"),
]
for fname, tid, test_path, file_path, msg in B_FIXTURES:
    _write(fname, _build(tid, [
        _span(tid, f"{tid}_root",  "turn",        t0=0, dur=9_000_000_000),
        _span(tid, f"{tid}_agent", "agent_run",   parent=f"{tid}_root", t0=100_000_000, dur=8_800_000_000),
        _span(tid, f"{tid}_s1",    "run_tests",   parent=f"{tid}_agent",t0=200_000_000, dur=2_000_000_000, attrs={"path": test_path}),
        _span(tid, f"{tid}_s2",    "edit_file",   parent=f"{tid}_agent",t0=2_300_000_000,dur=500_000_000,  attrs={"path": file_path}),
        _span(tid, f"{tid}_s3",    "git_commit",  parent=f"{tid}_agent",t0=2_900_000_000,dur=400_000_000,  attrs={"message": msg}),
        _span(tid, f"{tid}_s4",    "create_mr",   parent=f"{tid}_agent",t0=3_400_000_000,dur=600_000_000,  attrs={"target": f"fix/{test_path.split('/')[-1]}"}),
    ]))

# ── Pattern C: lint → format_code → git_commit ───────────────────────
C_FIXTURES = [
    ("poc_c1.json", "trace_c1", "backend/**", "style cleanup"),
    ("poc_c2.json", "trace_c2", "ui/**",      "format ts"),
    ("poc_c3.json", "trace_c3", "scripts/**", "lint fixes"),
]
for fname, tid, scope, msg in C_FIXTURES:
    _write(fname, _build(tid, [
        _span(tid, f"{tid}_root",  "turn",         t0=0, dur=4_000_000_000),
        _span(tid, f"{tid}_agent", "agent_run",    parent=f"{tid}_root", t0=100_000_000, dur=3_800_000_000),
        _span(tid, f"{tid}_s1",    "lint",         parent=f"{tid}_agent",t0=200_000_000,  dur=700_000_000, attrs={"scope": scope}),
        _span(tid, f"{tid}_s2",    "format_code",  parent=f"{tid}_agent",t0=1_000_000_000,dur=600_000_000, attrs={"scope": scope}),
        _span(tid, f"{tid}_s3",    "git_commit",   parent=f"{tid}_agent",t0=1_700_000_000,dur=400_000_000, attrs={"message": msg}),
    ]))

# ── Pattern D: edit → git_commit → git_push (conflicts with A) ──────
D_FIXTURES = [
    ("poc_d1.json", "trace_d1", "scripts/deploy.sh", "bump version"),
    ("poc_d2.json", "trace_d2", ".env.example",      "update env sample"),
    ("poc_d3.json", "trace_d3", "docs/notes.md",     "minor note"),
]
for fname, tid, path, msg in D_FIXTURES:
    _write(fname, _build(tid, [
        _span(tid, f"{tid}_root",  "turn",        t0=0, dur=3_000_000_000),
        _span(tid, f"{tid}_agent", "agent_run",   parent=f"{tid}_root", t0=100_000_000, dur=2_800_000_000),
        _span(tid, f"{tid}_s1",    "edit_file",   parent=f"{tid}_agent",t0=200_000_000, dur=400_000_000, attrs={"path": path}),
        _span(tid, f"{tid}_s2",    "git_commit",  parent=f"{tid}_agent",t0=700_000_000, dur=300_000_000, attrs={"message": msg}),
        _span(tid, f"{tid}_s3",    "git_push",    parent=f"{tid}_agent",t0=1_100_000_000,dur=500_000_000, attrs={"remote": "origin"}),
    ]))

# ── Pattern E: search_docs → answer_query ───────────────────────────
E_FIXTURES = [
    ("poc_e1.json", "trace_e1", "fastapi middleware lifecycle"),
    ("poc_e2.json", "trace_e2", "postgres index types"),
]
for fname, tid, q in E_FIXTURES:
    _write(fname, _build(tid, [
        _span(tid, f"{tid}_root",  "turn",          t0=0, dur=2_000_000_000),
        _span(tid, f"{tid}_agent", "agent_run",     parent=f"{tid}_root", t0=100_000_000, dur=1_800_000_000),
        _span(tid, f"{tid}_s1",    "search_docs",   parent=f"{tid}_agent",t0=200_000_000, dur=800_000_000, attrs={"query": q}),
        _span(tid, f"{tid}_s2",    "answer_query",  parent=f"{tid}_agent",t0=1_100_000_000,dur=700_000_000, attrs={"topic": q}),
    ]))

# ── Pattern F: failed commit (should not produce SOP) ───────────────
_write("poc_f1.json", _build("trace_f1", [
    _span("trace_f1", "trace_f1_root",  "turn",       t0=0, dur=2_000_000_000),
    _span("trace_f1", "trace_f1_agent", "agent_run",  parent="trace_f1_root", t0=100_000_000, dur=1_800_000_000),
    _span("trace_f1", "trace_f1_s1",    "edit_file",  parent="trace_f1_agent",t0=200_000_000, dur=400_000_000, attrs={"path": "src/broken.py"}),
    _span("trace_f1", "trace_f1_s2",    "git_commit", parent="trace_f1_agent",t0=700_000_000, dur=300_000_000, status="ERROR", attrs={"message": "commit failed: pre-commit hook"}),
]))

# ── Pattern G: noisy trace that could lure the LLM into hallucinating ─
noisy_spans = [
    _span("trace_g1", "trace_g1_root",  "turn",         t0=0, dur=3_500_000_000),
    _span("trace_g1", "trace_g1_agent", "agent_run",    parent="trace_g1_root", t0=100_000_000, dur=3_300_000_000),
]
for i in range(6):
    noisy_spans.append(_span(
        "trace_g1",
        f"trace_g1_n{i}",
        f"noop_{i}",
        parent="trace_g1_agent",
        t0=200_000_000 + i * 300_000_000,
        dur=200_000_000,
        attrs={"info": f"noise_{i}"},
    ))
_write("poc_g1.json", _build("trace_g1", noisy_spans))

print(f"Generated {len(list(POC_DIR.glob('*.json')))} traces in {POC_DIR}")
