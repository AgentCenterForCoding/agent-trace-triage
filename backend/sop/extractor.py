"""SOP induction: trace batch → LLM → validate → registry.

The LLM call is abstracted via `invoke_sop_llm(prompt) -> str` so tests can mock it.
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

import uuid

from . import registry
from .models import SOP, SOP_BASE, SOPCandidate, SOPMeta, SOPStep
from .prompts import build_sop_prompt
from .safety import scan_risky_terms

logger = logging.getLogger(__name__)


def invoke_sop_llm(prompt: str) -> str:
    """Default LLM caller. Phase 0: requires override in prod or mock in tests.

    Raises RuntimeError if no backing LLM is wired. Production wiring is left
    to a follow-up PR (Anthropic SDK / opencode CLI).
    """
    raise RuntimeError(
        "invoke_sop_llm not wired; inject via extractor.invoke_sop_llm = <callable> "
        "or pass llm=<callable> to extract_sops()."
    )


def _load_traces(trace_dir: Path) -> list[dict]:
    traces: list[dict] = []
    for p in sorted(trace_dir.glob("*.json")):
        try:
            traces.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning("failed to load %s: %s", p, exc)
    return traces


def _get_span_id(obj: dict) -> Optional[str]:
    for key in ("span_id", "spanId"):
        val = obj.get(key)
        if isinstance(val, str) and val:
            return val
    return None


def _collect_span_ids(traces) -> set[str]:
    ids: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            sid = _get_span_id(obj)
            if sid:
                ids.add(sid)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(traces)
    return ids


def _is_failed_status(status) -> bool:
    if isinstance(status, str):
        return status.upper() not in ("OK", "", "UNSET")
    if isinstance(status, dict):
        code = status.get("code")
        if isinstance(code, int):
            return code == 2
        if isinstance(code, str):
            return code.upper() not in ("OK", "UNSET", "0", "1")
    return False


def _collect_failed_span_ids(traces) -> set[str]:
    bad: set[str] = set()

    def walk(obj):
        if isinstance(obj, dict):
            if _is_failed_status(obj.get("status")):
                sid = _get_span_id(obj)
                if sid:
                    bad.add(sid)
            for v in obj.values():
                walk(v)
        elif isinstance(obj, list):
            for x in obj:
                walk(x)

    walk(traces)
    return bad


def validate_trace_refs(candidate: SOPCandidate, all_span_ids: set[str]) -> bool:
    for step in candidate.steps:
        if not step.trace_refs:
            return False
        for ref in step.trace_refs:
            if ref not in all_span_ids:
                return False
    return True


def _filter_failed_steps(candidate: SOPCandidate, failed_ids: set[str]) -> bool:
    """Return False if any candidate step references a failed span."""
    for step in candidate.steps:
        if any(ref in failed_ids for ref in step.trace_refs):
            return False
    return True


_SLOT_CANDIDATES = ("file_path", "path", "branch", "branch_name", "msg", "message", "target", "commit_id", "title")


def slotify(candidates: list[SOPCandidate]) -> list[SOPCandidate]:
    """Collapse candidates sharing the same action sequence into one with slotified args."""
    if len(candidates) < 2:
        return candidates
    buckets: dict[tuple[str, ...], list[SOPCandidate]] = defaultdict(list)
    for c in candidates:
        buckets[tuple(s.action for s in c.steps)].append(c)

    out: list[SOPCandidate] = []
    for actions, bucket in buckets.items():
        if len(bucket) == 1:
            out.append(bucket[0])
            continue
        merged_steps: list[SOPStep] = []
        for idx, action in enumerate(actions):
            all_args = [b.steps[idx].args for b in bucket]
            all_refs: list[str] = []
            for b in bucket:
                all_refs.extend(b.steps[idx].trace_refs)
            union_keys = set().union(*(a.keys() for a in all_args)) if all_args else set()
            new_args: dict = {}
            for key in union_keys:
                values = {a.get(key) for a in all_args if key in a}
                if len(values) == 1:
                    new_args[key] = next(iter(values))
                else:
                    new_args[key] = "{" + (key if key in _SLOT_CANDIDATES else f"slot_{key}") + "}"
            merged_steps.append(SOPStep(action=action, args=new_args, trace_refs=list(dict.fromkeys(all_refs))))
        source_ids: list[str] = []
        for b in bucket:
            source_ids.extend(b.source_trace_ids)
        out.append(SOPCandidate(
            name=bucket[0].name,
            intent=bucket[0].intent,
            tags=list({t for b in bucket for t in b.tags}),
            steps=merged_steps,
            source_trace_ids=list(dict.fromkeys(source_ids)),
            confidence=max(b.confidence for b in bucket),
        ))
    return out


def _parse_llm_json(raw: str) -> list[dict]:
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    text = m.group(1) if m else raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def extract_sops(
    traces: list[dict],
    *,
    llm=None,
) -> tuple[list[SOPCandidate], dict[str, int]]:
    """Induce SOP candidates from traces. Returns (candidates, stats).

    stats keys: produced, dropped_schema, dropped_hallucination, dropped_failed_step, flagged_risky.
    """
    caller = llm or invoke_sop_llm
    stats = {
        "produced": 0,
        "dropped_schema": 0,
        "dropped_hallucination": 0,
        "dropped_failed_step": 0,
        "flagged_risky": 0,
    }
    if not traces:
        return [], stats

    raw = caller(build_sop_prompt(json.dumps(traces, ensure_ascii=False)))
    entries = _parse_llm_json(raw)

    all_span_ids = _collect_span_ids(traces)
    failed_ids = _collect_failed_span_ids(traces)

    candidates: list[SOPCandidate] = []
    for entry in entries:
        try:
            cand = SOPCandidate(**entry)
        except Exception:
            stats["dropped_schema"] += 1
            continue
        if not validate_trace_refs(cand, all_span_ids):
            stats["dropped_hallucination"] += 1
            continue
        if not _filter_failed_steps(cand, failed_ids):
            stats["dropped_failed_step"] += 1
            continue
        candidates.append(cand)

    candidates = slotify(candidates)
    stats["produced"] = len(candidates)
    return candidates, stats


def _run_cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="backend.sop.extractor")
    parser.add_argument("--traces", required=True, help="Directory containing trace JSON files")
    parser.add_argument("--out", default=None, help="Output dir (unused; registry controls path)")
    parser.add_argument("--user", default=None, help="User id; defaults to OS login")
    args = parser.parse_args(argv)

    trace_dir = Path(args.traces)
    if not trace_dir.exists() or not trace_dir.is_dir():
        print(f"error: traces dir not found: {trace_dir}", file=sys.stderr)
        return 2

    if args.user:
        user_id = args.user
    else:
        try:
            user_id = os.environ.get("AGENT_TRIAGE_USER") or getpass.getuser()
        except Exception as exc:
            print(f"error: cannot resolve user_id: {exc}", file=sys.stderr)
            return 2
    if not user_id:
        print("error: empty user_id", file=sys.stderr)
        return 2

    traces = _load_traces(trace_dir)
    if not traces:
        print(json.dumps({"produced": 0, "dropped_hallucination": 0, "dropped_risky": 0, "total": 0}))
        return 0

    try:
        candidates, stats = extract_sops(traces)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    flagged_risky = 0
    for cand in candidates:
        body = cand.intent + " " + " ".join(s.action for s in cand.steps)
        hits = scan_risky_terms(body)
        sop = SOP(
            meta=SOPMeta(
                id=str(uuid.uuid4()),
                name=cand.name,
                tags=cand.tags,
                source_trace_ids=cand.source_trace_ids,
                confidence=cand.confidence,
                enabled=not hits,
                needs_review=bool(hits),
            ),
            intent=cand.intent,
            steps=cand.steps,
        )
        if hits:
            flagged_risky += 1
        try:
            registry.write(user_id, sop)
        except PermissionError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    summary = {
        "produced": stats["produced"],
        "dropped_hallucination": stats["dropped_hallucination"],
        "dropped_risky": flagged_risky,
        "total": len(traces),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0


def main() -> None:
    raise SystemExit(_run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
