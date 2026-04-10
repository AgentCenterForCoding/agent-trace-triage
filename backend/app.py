"""FastAPI application for Agent Trace Triage."""

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from models import TriageResult
from trace_parser import parse_otlp_json
from triage_engine import load_rules, triage

app = FastAPI(title="Agent Trace Triage", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).parent
SAMPLE_DIR = BASE_DIR / "sample_traces"
RULES_PATH = BASE_DIR / "rules.yaml"

# Load rules at startup
_rules = load_rules(RULES_PATH) if RULES_PATH.exists() else []


@app.post("/api/trace/upload")
async def upload_trace(file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and analyze an OTel Trace JSON file."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only .json files are accepted")

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    tree = parse_otlp_json(data)
    result = triage(tree, _rules)

    return {
        "trace_id": tree.trace_id,
        "span_count": len(tree.spans),
        "triage": result.model_dump(),
    }


@app.post("/api/trace/analyze")
async def analyze_trace(data: dict[str, Any]) -> dict[str, Any]:
    """Analyze an OTel Trace JSON payload directly."""
    tree = parse_otlp_json(data)
    result = triage(tree, _rules)

    return {
        "trace_id": tree.trace_id,
        "span_count": len(tree.spans),
        "triage": result.model_dump(),
    }


@app.get("/api/samples")
async def list_samples() -> list[dict[str, str]]:
    """List available sample traces."""
    if not SAMPLE_DIR.exists():
        return []

    samples = []
    for f in sorted(SAMPLE_DIR.glob("*.json")):
        samples.append({
            "name": f.stem,
            "filename": f.name,
        })
    return samples


@app.get("/api/samples/{name}")
async def get_sample(name: str) -> dict[str, Any]:
    """Load and analyze a sample trace by name."""
    sample_path = SAMPLE_DIR / f"{name}.json"
    if not sample_path.exists():
        raise HTTPException(404, f"Sample '{name}' not found")

    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tree = parse_otlp_json(data)
    result = triage(tree, _rules)

    return {
        "trace_id": tree.trace_id,
        "span_count": len(tree.spans),
        "raw_trace": data,
        "spans": [s.model_dump() for s in tree.spans.values()],
        "triage": result.model_dump(),
    }


# Serve frontend
FRONTEND_DIR = BASE_DIR.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def serve_frontend():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return index.read_text(encoding="utf-8")
        raise HTTPException(404, "Frontend not found")
