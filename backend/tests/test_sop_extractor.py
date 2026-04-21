"""Tests for backend.sop.extractor: schema drop, hallucination drop, failed-step filter, risky flag, slotify, CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sop import extractor, registry
from sop.models import SOPCandidate, SOPStep
from sop.safety import scan_risky_terms


SAMPLE_TRACE = [
    {
        "trace_id": "trace-A",
        "spans": [
            {"span_id": "s1", "name": "edit_file", "status": "OK"},
            {"span_id": "s2", "name": "git_commit", "status": "OK"},
            {"span_id": "s3", "name": "create_mr", "status": "OK"},
        ],
    }
]

SAMPLE_TRACE_WITH_FAILURE = [
    {
        "trace_id": "trace-B",
        "spans": [
            {"span_id": "f1", "name": "edit_file", "status": "OK"},
            {"span_id": "f2", "name": "git_commit", "status": "ERROR"},
        ],
    }
]


def _good_llm_output():
    return json.dumps([
        {
            "name": "commit-mr",
            "intent": "edit then commit then MR",
            "tags": ["git", "mr"],
            "steps": [
                {"action": "edit_file", "args": {"path": "{file_path}"}, "trace_refs": ["s1"]},
                {"action": "git_commit", "args": {"msg": "{msg}"}, "trace_refs": ["s2"]},
                {"action": "create_mr", "args": {"target": "{branch}"}, "trace_refs": ["s3"]},
            ],
            "source_trace_ids": ["trace-A"],
            "confidence": 0.9,
        }
    ])


def test_extract_valid_sop():
    cands, stats = extract_with(_good_llm_output(), SAMPLE_TRACE)
    assert len(cands) == 1
    assert stats["dropped_hallucination"] == 0
    assert cands[0].steps[0].trace_refs == ["s1"]


def test_hallucinated_span_dropped():
    bad = json.dumps([
        {
            "name": "hallucinated",
            "intent": "fake",
            "tags": [],
            "steps": [
                {"action": "edit_file", "args": {}, "trace_refs": ["nonexistent-span"]},
            ],
            "source_trace_ids": [],
            "confidence": 0.5,
        }
    ])
    cands, stats = extract_with(bad, SAMPLE_TRACE)
    assert cands == []
    assert stats["dropped_hallucination"] == 1


def test_schema_violation_dropped():
    malformed = json.dumps([{"name": "broken"}])
    cands, stats = extract_with(malformed, SAMPLE_TRACE)
    assert cands == []
    assert stats["dropped_schema"] == 1


def test_failed_step_filtered():
    output = json.dumps([
        {
            "name": "partial",
            "intent": "edit ok, commit failed",
            "tags": [],
            "steps": [
                {"action": "edit_file", "args": {}, "trace_refs": ["f1"]},
                {"action": "git_commit", "args": {}, "trace_refs": ["f2"]},
            ],
            "source_trace_ids": ["trace-B"],
            "confidence": 0.7,
        }
    ])
    cands, stats = extract_with(output, SAMPLE_TRACE_WITH_FAILURE)
    assert cands == []
    assert stats["dropped_failed_step"] == 1


def test_risky_terms_detected_in_body():
    # Safety scanner is unit-level; extractor uses it at CLI layer.
    assert scan_risky_terms("请自动执行 git push -f") != []
    assert scan_risky_terms("请创建一个 MR 作为建议") == []


def test_slotify_merges_variants():
    c1 = SOPCandidate(
        name="edit-commit",
        intent="i",
        tags=[],
        steps=[
            SOPStep(action="edit_file", args={"path": "a.py"}, trace_refs=["s1"]),
            SOPStep(action="git_commit", args={"msg": "fix A"}, trace_refs=["s2"]),
        ],
        source_trace_ids=["t1"],
        confidence=0.5,
    )
    c2 = SOPCandidate(
        name="edit-commit",
        intent="i",
        tags=[],
        steps=[
            SOPStep(action="edit_file", args={"path": "b.py"}, trace_refs=["s11"]),
            SOPStep(action="git_commit", args={"msg": "fix B"}, trace_refs=["s12"]),
        ],
        source_trace_ids=["t2"],
        confidence=0.6,
    )
    merged = extractor.slotify([c1, c2])
    assert len(merged) == 1
    assert "{" in str(merged[0].steps[0].args.get("path"))


def extract_with(llm_output: str, traces):
    return extractor.extract_sops(traces, llm=lambda prompt: llm_output)


def test_cli_rejects_missing_traces_dir(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "sop.extractor", "--traces", str(tmp_path / "nope")],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout.strip() == ""


def test_cli_empty_dir_returns_zero_summary(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    result = subprocess.run(
        [sys.executable, "-m", "sop.extractor", "--traces", str(empty), "--user", "alice"],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    summary = json.loads(result.stdout.strip())
    assert summary["produced"] == 0
    assert summary["total"] == 0
