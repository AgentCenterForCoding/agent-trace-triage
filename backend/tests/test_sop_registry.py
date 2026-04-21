"""Tests for backend.sop.registry: path isolation, dedup, conflict, retrieve filters."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sop import registry
from sop.models import SOP, SOPCandidate, SOPMeta, SOPStep


@pytest.fixture
def tmp_sop_base(tmp_path, monkeypatch):
    base = tmp_path / "sops"
    base.mkdir()
    monkeypatch.setattr(registry, "SOP_BASE", base)
    from sop import models

    monkeypatch.setattr(models, "SOP_BASE", base)
    return base


def _candidate(name="commit-mr", actions=("edit_file", "git_commit", "create_mr"), tags=("git",)):
    return SOPCandidate(
        name=name,
        intent=f"intent for {name}",
        tags=list(tags),
        steps=[SOPStep(action=a, args={}, trace_refs=[f"span-{i}"]) for i, a in enumerate(actions)],
        source_trace_ids=["trace-A"],
        confidence=0.8,
    )


def test_path_traversal_raises(tmp_sop_base):
    with pytest.raises(PermissionError):
        registry.list_("../other")
    with pytest.raises(PermissionError):
        registry.write("..", _candidate())


def test_list_isolation(tmp_sop_base):
    registry.write("alice", _candidate(name="alice-sop"))
    registry.write("bob", _candidate(name="bob-sop"))
    alice_metas = registry.list_("alice")
    bob_metas = registry.list_("bob")
    assert len(alice_metas) == 1 and alice_metas[0].name == "alice-sop"
    assert len(bob_metas) == 1 and bob_metas[0].name == "bob-sop"


def test_list_missing_dir_returns_empty(tmp_sop_base):
    assert registry.list_("newuser") == []


def test_dedup_bumps_version(tmp_sop_base):
    c1 = _candidate()
    c2 = _candidate()
    c2.source_trace_ids = ["trace-B"]
    p1 = registry.write("alice", c1)
    p2 = registry.write("alice", c2)
    assert p1 == p2
    metas = registry.list_("alice")
    assert len(metas) == 1
    assert metas[0].version == 2
    assert set(metas[0].source_trace_ids) == {"trace-A", "trace-B"}


def test_conflict_marks_both(tmp_sop_base):
    mr_cand = _candidate(name="MR-path", actions=("edit_file", "git_commit", "create_mr"))
    push_cand = _candidate(name="push-path", actions=("edit_file", "git_commit", "git_push"))
    registry.write("alice", mr_cand)
    registry.write("alice", push_cand)

    metas = registry.list_("alice")
    assert len(metas) == 2
    assert all(m.needs_review for m in metas)
    ids = {m.id for m in metas}
    for m in metas:
        assert set(m.conflict_with) & (ids - {m.id})


def test_retrieve_excludes_disabled(tmp_sop_base):
    registry.write("alice", _candidate(name="ok"))
    # Write a manually-disabled SOP.
    sop = SOP(
        meta=SOPMeta(id="x", name="disabled", enabled=False),
        intent="should not show",
        steps=[SOPStep(action="noop", args={}, trace_refs=["span-x"])],
    )
    registry.write("alice", sop)

    default = registry.retrieve("alice", query=None, k=5)
    assert all(s.meta.enabled and not s.meta.needs_review for s in default)

    all_ = registry.retrieve("alice", query=None, k=5, include_disabled=True)
    names = {s.meta.name for s in all_}
    assert "disabled" in names


def test_retrieve_top_k(tmp_sop_base):
    for i in range(5):
        registry.write("alice", _candidate(name=f"sop-{i}", actions=(f"action_{i}",), tags=("git",)))
    out = registry.retrieve("alice", query=None, k=3)
    assert len(out) == 3
