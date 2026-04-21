"""End-to-end smoke: extractor (mocked LLM) → registry → API endpoint → hook_cli output."""

import io
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from sop import extractor, hook_cli, registry
from sop.models import SOPCandidate, SOPStep


def test_e2e_pipeline(tmp_path, monkeypatch):
    base = tmp_path / "sops"
    base.mkdir()
    monkeypatch.setattr(registry, "SOP_BASE", base)
    from sop import models

    monkeypatch.setattr(models, "SOP_BASE", base)

    traces = [{
        "trace_id": "trace-A",
        "spans": [
            {"span_id": "s1", "name": "edit_file", "status": "OK"},
            {"span_id": "s2", "name": "git_commit", "status": "OK"},
            {"span_id": "s3", "name": "create_mr", "status": "OK"},
        ],
    }]
    llm_output = json.dumps([{
        "name": "commit-mr",
        "intent": "edit then commit then MR",
        "tags": ["git", "mr"],
        "steps": [
            {"action": "edit_file", "args": {}, "trace_refs": ["s1"]},
            {"action": "git_commit", "args": {}, "trace_refs": ["s2"]},
            {"action": "create_mr", "args": {}, "trace_refs": ["s3"]},
        ],
        "source_trace_ids": ["trace-A"],
        "confidence": 0.9,
    }])

    cands, stats = extractor.extract_sops(traces, llm=lambda _prompt: llm_output)
    assert stats["produced"] == 1
    for c in cands:
        registry.write("alice", c)

    client = TestClient(app)
    r = client.get("/api/v1/sops/retrieve", params={"user_id": "alice", "k": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert "create_mr" in body[0]["body"]

    monkeypatch.setenv("AGENT_TRIAGE_USER", "alice")
    monkeypatch.setattr(hook_cli, "_fetch_sops", lambda _u: body)
    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    assert hook_cli.main() == 0
    out = stdout.getvalue()
    assert hook_cli.HEADER in out
    assert "create_mr" in out
    assert hook_cli.FOOTER in out
