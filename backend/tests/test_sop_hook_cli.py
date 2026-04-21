"""Tests for backend.sop.hook_cli: normal path, empty, byte cap, backend-unavailable graceful exit."""

import io
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sop import hook_cli


def _run(monkeypatch, user="alice", api_returns=None, raise_exc=None, env=None):
    env = env or {}
    monkeypatch.setenv("AGENT_TRIAGE_USER", user)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    def fake_fetch(u):
        if raise_exc:
            raise raise_exc
        return api_returns or []

    monkeypatch.setattr(hook_cli, "_fetch_sops", fake_fetch)

    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    exit_code = hook_cli.main()
    return exit_code, stdout.getvalue(), stderr.getvalue()


def test_normal_path(monkeypatch):
    items = [{"meta": {"id": "1"}, "body": "## 意图\nedit then commit then MR"}]
    code, out, err = _run(monkeypatch, api_returns=items)
    assert code == 0
    assert hook_cli.HEADER in out
    assert hook_cli.FOOTER in out
    assert "edit then commit then MR" in out


def test_empty_result_empty_stdout(monkeypatch):
    code, out, err = _run(monkeypatch, api_returns=[])
    assert code == 0
    assert out == ""


def test_backend_unavailable_silent(monkeypatch):
    code, out, err = _run(monkeypatch, raise_exc=ConnectionError("refused"))
    assert code == 0
    assert out == ""
    assert "unavailable" in err.lower() or "refused" in err.lower()


def test_byte_cap_drops_low_ranked(monkeypatch):
    big_body = "x" * 5000
    items = [
        {"meta": {"id": "1"}, "body": big_body},
        {"meta": {"id": "2"}, "body": big_body},
        {"meta": {"id": "3"}, "body": big_body},
    ]
    code, out, err = _run(monkeypatch, api_returns=items)
    assert code == 0
    assert len(out.encode("utf-8")) <= hook_cli.BYTE_CAP
    assert "dropped" in err


def test_missing_user_returns_exit2(monkeypatch):
    monkeypatch.delenv("AGENT_TRIAGE_USER", raising=False)
    monkeypatch.setattr(hook_cli, "_resolve_user", lambda: None)

    stdout = io.StringIO()
    stderr = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    monkeypatch.setattr(sys, "stderr", stderr)
    code = hook_cli.main()
    assert code == 2
    assert stdout.getvalue() == ""
