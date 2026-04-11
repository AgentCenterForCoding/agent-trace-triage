"""FastAPI application for Agent Trace Triage."""

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from models import TriageResult
from router import LLMConfig, parse_llm_config_from_headers
from trace_parser import parse_otlp_json
from triage_engine import load_rules, triage, triage_hybrid

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


def _get_llm_config(request: Request) -> Optional[LLMConfig]:
    """Extract LLM config from request headers."""
    headers = {k.lower(): v for k, v in request.headers.items()}
    return parse_llm_config_from_headers(headers)


@app.post("/api/trace/upload")
async def upload_trace(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
    """Upload and analyze an OTel Trace JSON file."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(400, "Only .json files are accepted")

    content = await file.read()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")

    tree = parse_otlp_json(data)
    llm_config = _get_llm_config(request)
    result = triage_hybrid(tree, _rules, llm_config)

    return {
        "trace_id": tree.trace_id,
        "span_count": len(tree.spans),
        "triage": result.model_dump(),
    }


@app.post("/api/trace/analyze")
async def analyze_trace(request: Request, data: dict[str, Any]) -> dict[str, Any]:
    """Analyze an OTel Trace JSON payload directly."""
    tree = parse_otlp_json(data)
    llm_config = _get_llm_config(request)
    result = triage_hybrid(tree, _rules, llm_config)

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
async def get_sample(request: Request, name: str) -> dict[str, Any]:
    """Load and analyze a sample trace by name."""
    sample_path = SAMPLE_DIR / f"{name}.json"
    if not sample_path.exists():
        raise HTTPException(404, f"Sample '{name}' not found")

    with open(sample_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tree = parse_otlp_json(data)
    llm_config = _get_llm_config(request)
    result = triage_hybrid(tree, _rules, llm_config)

    return {
        "trace_id": tree.trace_id,
        "span_count": len(tree.spans),
        "raw_trace": data,
        "spans": [s.model_dump() for s in tree.spans.values()],
        "triage": result.model_dump(),
    }


@app.post("/api/llm/test-connection")
async def test_llm_connection(request: Request) -> dict[str, Any]:
    """Test LLM API connectivity with a minimal request."""
    llm_config = _get_llm_config(request)
    if not llm_config:
        raise HTTPException(400, "LLM configuration missing or disabled in request headers")

    from llm_skill import LLMInvocationError
    import json as _json
    import logging

    logger = logging.getLogger(__name__)

    try:
        import httpx
        from anthropic import Anthropic, APIError, APITimeoutError

        # Use trust_env=False to prevent httpx from reading proxy env vars
        # (the proxy often can't reach non-Anthropic endpoints like DashScope)
        http_client = httpx.Client(timeout=llm_config.timeout, trust_env=False)

        client = Anthropic(
            api_key=llm_config.api_key,
            base_url=llm_config.base_url,
            timeout=llm_config.timeout,
            http_client=http_client,
        )

        response = client.messages.create(
            model=llm_config.model,
            max_tokens=32,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        )

        reply_text = ""
        for content in response.content:
            if hasattr(content, "text"):
                reply_text = content.text
                break

        return {
            "status": "ok",
            "model": llm_config.model,
            "reply": reply_text.strip(),
            "message": f"Successfully connected to {llm_config.base_url} using model {llm_config.model}",
        }

    except APITimeoutError as e:
        return {"status": "error", "message": f"Connection timeout: {e}"}
    except APIError as e:
        return {"status": "error", "message": f"API error: {e}"}
    except Exception as e:
        return {"status": "error", "message": f"Connection failed: {e}"}


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
