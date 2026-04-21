"""Measure P99 latency of hook_cli against a REAL running backend (uvicorn)."""

from __future__ import annotations

import json
import os
import signal
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from sop import extractor, models as sop_models, registry
from sop.safety import scan_risky_terms
from stub_llm import make_stub_llm


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _wait_ready(port: int, timeout=10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _seed_registry(base: Path):
    sop_models.SOP_BASE = base
    registry.SOP_BASE = base
    # Seed 50 SOPs for a realistic retrieval load.
    # Start from the 20 POC traces, then synthesize 30 more by varying action names.
    trace_dir = Path(__file__).parent / "traces"
    stub = make_stub_llm()
    all_traces = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(trace_dir.glob("*.json"))]
    for trace in all_traces:
        cands, _ = extractor.extract_sops([trace], llm=stub)
        for c in cands:
            body = c.intent + " " + " ".join(s.action for s in c.steps)
            hits = scan_risky_terms(body)
            sop = sop_models.SOP(
                meta=sop_models.SOPMeta(
                    id=f"poc_{c.name}_{os.urandom(2).hex()}",
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
            registry.write("poc_user", sop)

    # Pad with synthetic SOPs up to 50 total.
    existing = len(list((base / "poc_user").glob("*.md")))
    from sop.models import SOPStep
    i = 0
    while existing < 50:
        sop = sop_models.SOP(
            meta=sop_models.SOPMeta(
                id=f"synth_{i}",
                name=f"synth-sop-{i}",
                tags=["synth"],
                source_trace_ids=[f"trace_synth_{i}"],
                confidence=0.5,
            ),
            intent=f"synthetic SOP #{i}",
            steps=[SOPStep(action=f"synth_action_{i}", args={}, trace_refs=[f"span_{i}"])],
        )
        registry.write("poc_user", sop)
        i += 1
        existing += 1


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "sops"
        base.mkdir()
        _seed_registry(base)

        port = _free_port()
        backend_dir = str(PROJECT_ROOT / "backend")
        env = dict(os.environ)
        env["PYTHONPATH"] = backend_dir + os.pathsep + env.get("PYTHONPATH", "")
        env["AGENT_TRIAGE_SOP_BASE"] = str(base)  # not read by code; for debug only

        # Monkey-patch: we need the subprocess backend to use the temp sops dir.
        # Simplest: write a small wrapper that sets SOP_BASE before importing main.
        wrapper = Path(tmp) / "bootstrap.py"
        wrapper.write_text(f"""import sys
sys.path.insert(0, r'{backend_dir}')
from pathlib import Path
from sop import models, registry
models.SOP_BASE = Path(r'{base}')
registry.SOP_BASE = Path(r'{base}')
import uvicorn
from main import app
uvicorn.run(app, host='127.0.0.1', port={port}, log_level='warning')
""", encoding="utf-8")

        proc = subprocess.Popen(
            [sys.executable, str(wrapper)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        try:
            if not _wait_ready(port):
                print("backend failed to start", file=sys.stderr)
                proc.terminate()
                return 1

            os.environ["AGENT_TRIAGE_API_URL"] = f"http://127.0.0.1:{port}"
            os.environ["AGENT_TRIAGE_USER"] = "poc_user"

            # Import hook_cli AFTER env vars set; run it 30 times measuring wall clock.
            from sop import hook_cli
            import io

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
            p50 = latencies[len(latencies) // 2]
            p99 = latencies[max(0, int(len(latencies) * 0.99) - 1)]
            mean = statistics.mean(latencies)

            print(json.dumps({
                "sops_seeded": len(list((base / "poc_user").glob("*.md"))),
                "p50_ms": round(p50, 2),
                "p99_ms": round(p99, 2),
                "mean_ms": round(mean, 2),
                "min_ms": round(min(latencies), 2),
                "max_ms": round(max(latencies), 2),
                "runs": len(latencies),
                "p99_lt_200ms": p99 < 200,
            }, indent=2))
        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    main()
