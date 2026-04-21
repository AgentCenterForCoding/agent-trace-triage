"""Tests for /api/v1/sops/retrieve endpoint: success, validation, path traversal."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from sop import registry
from sop.models import SOPCandidate, SOPStep


@pytest.fixture
def client(tmp_path, monkeypatch):
    base = tmp_path / "sops"
    base.mkdir()
    monkeypatch.setattr(registry, "SOP_BASE", base)
    from sop import models

    monkeypatch.setattr(models, "SOP_BASE", base)
    return TestClient(app)


def _seed(user="alice", name="demo"):
    cand = SOPCandidate(
        name=name,
        intent="i",
        tags=["git"],
        steps=[SOPStep(action="git_commit", args={}, trace_refs=["s1"])],
        source_trace_ids=["t-1"],
        confidence=0.5,
    )
    registry.write(user, cand)


def test_retrieve_returns_sops(client):
    _seed()
    r = client.get("/api/v1/sops/retrieve", params={"user_id": "alice", "k": 3})
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert "meta" in body[0] and "body" in body[0]
    assert body[0]["meta"]["name"] == "demo"


def test_retrieve_missing_user_id_returns_422(client):
    r = client.get("/api/v1/sops/retrieve")
    assert r.status_code == 422


def test_retrieve_empty_user_id_returns_422(client):
    r = client.get("/api/v1/sops/retrieve", params={"user_id": ""})
    assert r.status_code == 422


def test_retrieve_path_traversal_returns_403(client):
    r = client.get("/api/v1/sops/retrieve", params={"user_id": "../other"})
    assert r.status_code == 403
    assert "invalid" in r.json()["detail"].lower()


def test_retrieve_k_out_of_range_returns_422(client):
    r = client.get("/api/v1/sops/retrieve", params={"user_id": "alice", "k": 0})
    assert r.status_code == 422
    r = client.get("/api/v1/sops/retrieve", params={"user_id": "alice", "k": 100})
    assert r.status_code == 422


def test_retrieve_empty_returns_empty_list(client):
    r = client.get("/api/v1/sops/retrieve", params={"user_id": "newuser"})
    assert r.status_code == 200
    assert r.json() == []
