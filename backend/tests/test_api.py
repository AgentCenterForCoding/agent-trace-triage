"""Backend API integration tests.

Tests the API endpoints without calling the real opencode CLI.
The triage endpoint is tested with a mock of run_triage to avoid
external dependencies and long execution times.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# Adjust sys.path so imports from backend/ work
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from main import app
from services.storage import SETTINGS_FILE, SettingsConfig, save_settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_settings():
    """Remove settings file before/after each test."""
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()
    yield
    if SETTINGS_FILE.exists():
        SETTINGS_FILE.unlink()


SAMPLE_TRACES_DIR = Path(__file__).parent.parent.parent / "sample_traces"


# ── Health ──────────────────────────────────────────────────

def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Samples ─────────────────────────────────────────────────

def test_list_samples(client):
    r = client.get("/api/v1/samples")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0
    assert "filename" in data[0]
    assert "size_bytes" in data[0]


def test_get_sample(client):
    r = client.get("/api/v1/samples")
    first = r.json()[0]["filename"]
    r2 = client.get(f"/api/v1/samples/{first}")
    assert r2.status_code == 200
    assert "resourceSpans" in r2.json()


def test_get_sample_not_found(client):
    r = client.get("/api/v1/samples/nonexistent.json")
    assert r.status_code == 404


def test_get_sample_path_traversal(client):
    r = client.get("/api/v1/samples/..%2F..%2Fmain.py")
    assert r.status_code in (400, 404)


# ── Settings ────────────────────────────────────────────────

def test_get_settings_default(client):
    r = client.get("/api/v1/settings")
    assert r.status_code == 200
    data = r.json()
    assert data["api_key_configured"] is False
    assert data["auth_enabled"] is False


def test_update_settings(client):
    r = client.post(
        "/api/v1/settings",
        json={"api_key": "test-key-123", "auth_enabled": True},
    )
    assert r.status_code == 200

    r2 = client.get("/api/v1/settings")
    data = r2.json()
    assert data["api_key_configured"] is True
    assert data["auth_enabled"] is True


def test_api_key_auth_blocks_without_key(client):
    save_settings(SettingsConfig(api_key="secret", auth_enabled=True))
    r = client.get("/api/v1/samples")
    assert r.status_code == 401


def test_api_key_auth_allows_with_key(client):
    save_settings(SettingsConfig(api_key="secret", auth_enabled=True))
    r = client.get("/api/v1/samples", headers={"X-API-Key": "secret"})
    assert r.status_code == 200


def test_settings_endpoint_bypasses_auth(client):
    save_settings(SettingsConfig(api_key="secret", auth_enabled=True))
    r = client.get("/api/v1/settings")
    assert r.status_code == 200


# ── Triage SSE (mocked) ────────────────────────────────────

async def _mock_run_triage(trace_json, enable_llm=True):
    """Simulate a successful triage yielding progress + result."""
    yield {"type": "progress", "stage": "start", "message": "开始归因分析..."}
    yield {"type": "progress", "stage": "thinking", "message": "Agent 开始分析..."}
    yield {
        "type": "result",
        "data": {
            "primary_owner": "model_team",
            "co_responsible": ["agent_team"],
            "confidence": 0.9,
            "fault_span": {
                "span_id": "001",
                "name": "model_inference",
                "status": "ERROR",
                "status_message": "TimeoutError",
            },
            "fault_chain": [],
            "root_cause": "Model timeout",
            "action_items": ["Fix timeout"],
            "source": "rules",
            "reasoning": "L1 match",
        },
    }


@patch("routes.triage.run_triage", side_effect=_mock_run_triage)
def test_triage_sse(mock_triage, client):
    trace = {"resourceSpans": []}
    r = client.post(
        "/api/v1/triage",
        json={"trace": trace, "enable_llm": False},
    )
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    lines = r.text.strip().split("\n\n")
    events = []
    for block in lines:
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))

    assert len(events) >= 2
    result_events = [e for e in events if "primary_owner" in e]
    assert len(result_events) == 1
    assert result_events[0]["primary_owner"] == "model_team"


async def _mock_run_triage_error(trace_json, enable_llm=True):
    yield {"type": "progress", "stage": "start", "message": "开始..."}
    yield {"type": "error", "message": "opencode 命令未找到"}


@patch("routes.triage.run_triage", side_effect=_mock_run_triage_error)
def test_triage_sse_error(mock_triage, client):
    r = client.post("/api/v1/triage", json={"trace": {}})
    assert r.status_code == 200
    assert "error" in r.text


# ── Triage async (mocked) ──────────────────────────────────

@patch("routes.triage.run_triage", side_effect=_mock_run_triage)
def test_triage_async_creates_task(mock_triage, client):
    r = client.post("/api/v1/triage/async", json={"trace": {}})
    assert r.status_code == 200
    data = r.json()
    assert "task_id" in data
    assert data["status"] in ("completed", "pending", "processing")


@patch("routes.triage.run_triage", side_effect=_mock_run_triage)
def test_triage_task_status(mock_triage, client):
    r = client.post("/api/v1/triage/async", json={"trace": {}})
    task_id = r.json()["task_id"]
    r2 = client.get(f"/api/v1/triage/{task_id}")
    assert r2.status_code == 200
    assert r2.json()["task_id"] == task_id


def test_triage_task_not_found(client):
    r = client.get("/api/v1/triage/nonexistent-id")
    assert r.status_code == 404
