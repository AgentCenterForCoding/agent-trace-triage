"""Dump every SOP written during run_poc.py (re-runs the pipeline for inspection)."""

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).parent))

from sop import extractor, models as sop_models, registry
from sop.safety import scan_risky_terms
from stub_llm import make_stub_llm


def _tid(trace):
    for rs in trace.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            for sp in ss.get("spans", []):
                return sp.get("traceId") or sp.get("trace_id")
    return ""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "sops"
        base.mkdir()
        sop_models.SOP_BASE = base
        registry.SOP_BASE = base

        stub = make_stub_llm()
        traces = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((Path(__file__).parent / "traces").glob("*.json"))]
        for trace in traces:
            tid = _tid(trace)
            cands, _ = extractor.extract_sops([trace], llm=stub)
            for c in cands:
                body = c.intent + " " + " ".join(s.action for s in c.steps)
                hits = scan_risky_terms(body)
                sop = sop_models.SOP(
                    meta=sop_models.SOPMeta(
                        id=f"{tid}_sop_{c.name}",
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

        rows = []
        for m in registry.list_("poc_user"):
            rows.append({
                "name": m.name,
                "version": m.version,
                "enabled": m.enabled,
                "needs_review": m.needs_review,
                "conflict_with": m.conflict_with,
                "source_traces": m.source_trace_ids,
                "n_sources": len(m.source_trace_ids),
            })
        print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
