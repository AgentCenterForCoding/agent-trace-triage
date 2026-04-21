"""POC validator: runs extractor (stub LLM) → registry → API → hook_cli.

Reports on three GO criteria:
  (1) SOP induction F1 ≥ 0.75 (macro-F1 over 20 annotated traces).
  (2) Injection latency P99 < 200ms across 30 warm hook_cli invocations.
  (3) Safety: hallucinated / failed-step / risky SOPs correctly dropped or flagged.

Usage:
  python tests/poc/run_poc.py
"""

from __future__ import annotations

import io
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from sop import extractor, hook_cli, registry
from sop import models as sop_models
from stub_llm import make_stub_llm

TRACE_DIR = Path(__file__).parent / "traces"
GOLDEN_PATH = Path(__file__).parent / "golden_sops.json"


def _load_poc_traces() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(TRACE_DIR.glob("*.json"))]


def _trace_id(trace: dict) -> str:
    for rs in trace.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for sp in ss.get("spans", []):
                tid = sp.get("traceId") or sp.get("trace_id")
                if tid:
                    return tid
    return ""


def _score(predicted_sequences: dict[str, list[str]], golden: dict[str, list[str]]) -> dict[str, float]:
    """Compute macro F1 on action-sequence match.

    For each trace with a non-empty golden SOP, prediction counts as TP iff
    one of the emitted SOPs' action sequences equals the golden sequence.
    Empty-golden traces count as TN iff no SOP was emitted for them.
    """
    tp = fp = fn = tn = 0
    per_trace = {}
    for tid, golden_seq in golden.items():
        pred_seqs = predicted_sequences.get(tid, [])
        if golden_seq:
            hit = any(seq == golden_seq for seq in pred_seqs)
            if hit:
                tp += 1
                per_trace[tid] = "TP"
            else:
                fn += 1
                per_trace[tid] = "FN"
        else:
            if pred_seqs:
                fp += 1
                per_trace[tid] = "FP"
            else:
                tn += 1
                per_trace[tid] = "TN"

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "per_trace": per_trace,
    }


def _measure_real_latency(base: Path) -> dict:
    """Spin a real uvicorn, run hook_cli 30× against it, return latency summary."""
    import importlib
    import os
    import socket
    import subprocess

    def free_port():
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def wait_ready(port, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                    return True
            except OSError:
                time.sleep(0.1)
        return False

    port = free_port()
    backend_dir = str(PROJECT_ROOT / "backend")
    env = dict(os.environ)
    env["PYTHONPATH"] = backend_dir + os.pathsep + env.get("PYTHONPATH", "")

    wrapper = base.parent / "bootstrap.py"
    wrapper.write_text(
        f"""import sys
sys.path.insert(0, r'{backend_dir}')
from pathlib import Path
from sop import models, registry
models.SOP_BASE = Path(r'{base}')
registry.SOP_BASE = Path(r'{base}')
import uvicorn
from main import app
uvicorn.run(app, host='127.0.0.1', port={port}, log_level='warning')
""",
        encoding="utf-8",
    )

    proc = subprocess.Popen(
        [sys.executable, str(wrapper)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if not wait_ready(port):
            return {"p99_ms": None, "error": "backend failed to start"}

        os.environ["AGENT_TRIAGE_API_URL"] = f"http://127.0.0.1:{port}"
        os.environ["AGENT_TRIAGE_USER"] = "poc_user"
        importlib.reload(hook_cli)

        latencies = []
        for _ in range(30):
            stdout = io.StringIO()
            stderr = io.StringIO()
            prev_out, prev_err = sys.stdout, sys.stderr
            sys.stdout, sys.stderr = stdout, stderr
            t0 = time.perf_counter()
            try:
                hook_cli.main()
            finally:
                sys.stdout, sys.stderr = prev_out, prev_err
            latencies.append((time.perf_counter() - t0) * 1000.0)
        latencies.sort()
        return {
            "p50_ms": round(latencies[len(latencies) // 2], 2),
            "p99_ms": round(latencies[max(0, int(len(latencies) * 0.99) - 1)], 2),
            "mean_ms": round(statistics.mean(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "runs": len(latencies),
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def main() -> int:
    # 1) Redirect registry to temp dir.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "sops"
        tmp_path.mkdir()
        original_base = sop_models.SOP_BASE
        sop_models.SOP_BASE = tmp_path
        registry.SOP_BASE = tmp_path

        golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        traces = _load_poc_traces()
        assert len(traces) == 20, f"expected 20 POC traces, got {len(traces)}"

        stub = make_stub_llm()

        # 2) Induction (one trace at a time so we can attribute SOPs to traces).
        per_trace_pred: dict[str, list[list[str]]] = {}
        agg_stats = {"produced": 0, "dropped_schema": 0, "dropped_hallucination": 0, "dropped_failed_step": 0}
        risky_flags = 0

        for trace in traces:
            tid = _trace_id(trace)
            cands, stats = extractor.extract_sops([trace], llm=stub)
            for k in agg_stats:
                agg_stats[k] += stats.get(k, 0)
            seqs: list[list[str]] = []
            for c in cands:
                seqs.append([s.action for s in c.steps])
                body = c.intent + " " + " ".join(s.action for s in c.steps)
                from sop.safety import scan_risky_terms
                hits = scan_risky_terms(body)
                sop = sop_models.SOP(
                    meta=sop_models.SOPMeta(
                        id=f"{tid}_sop_{len(seqs)}",
                        name=c.name,
                        tags=c.tags,
                        source_trace_ids=c.source_trace_ids,
                        confidence=c.confidence,
                        enabled=not hits,
                        needs_review=bool(hits),
                    ),
                    intent=c.intent,
                    steps=c.steps,
                )
                if hits:
                    risky_flags += 1
                registry.write("poc_user", sop)
            per_trace_pred[tid] = seqs

        # 3) Score F1.
        predicted_sequences = {tid: seqs for tid, seqs in per_trace_pred.items()}
        score = _score(predicted_sequences, golden)

        # 4) Pad registry up to 50 SOPs so latency measurement reflects
        # the spec's "50-SOP scale" scenario.
        from sop.models import SOPStep
        existing_count = len(list((tmp_path / "poc_user").glob("*.md")))
        synth_i = 0
        while existing_count < 50:
            registry.write("poc_user", sop_models.SOP(
                meta=sop_models.SOPMeta(
                    id=f"synth_{synth_i}",
                    name=f"synth-sop-{synth_i}",
                    tags=["synth"],
                ),
                intent=f"synthetic SOP #{synth_i}",
                steps=[SOPStep(action=f"synth_action_{synth_i}", args={}, trace_refs=[f"span_{synth_i}"])],
            ))
            synth_i += 1
            existing_count += 1

        latency = _measure_real_latency(tmp_path)
        p99 = latency.get("p99_ms") or float("inf")

        # 5) Compose report.
        all_metas = registry.list_("poc_user")
        enabled = [m for m in all_metas if m.enabled and not m.needs_review]
        flagged = [m for m in all_metas if m.needs_review]

        report = {
            "traces_total": len(traces),
            "sops_in_registry": len(all_metas),
            "sops_enabled": len(enabled),
            "sops_flagged": len(flagged),
            "induction": {
                "produced": agg_stats["produced"],
                "dropped_schema": agg_stats["dropped_schema"],
                "dropped_hallucination": agg_stats["dropped_hallucination"],
                "dropped_failed_step": agg_stats["dropped_failed_step"],
                "flagged_risky": risky_flags,
            },
            "score": {k: v for k, v in score.items() if k != "per_trace"},
            "per_trace": score["per_trace"],
            "latency": latency,
            "gate": {
                "f1_ge_0_75": score["f1"] >= 0.75,
                "p99_lt_200ms": p99 < 200,
                "hallucination_dropped": agg_stats["dropped_hallucination"] >= 1,
                "failed_step_dropped": agg_stats["dropped_failed_step"] >= 1,
                "risky_flagged": risky_flags >= 1,
            },
        }

        sop_models.SOP_BASE = original_base
        registry.SOP_BASE = original_base

        print(json.dumps(report, ensure_ascii=False, indent=2))

        all_green = all(report["gate"].values())
        return 0 if all_green else 1


if __name__ == "__main__":
    raise SystemExit(main())
