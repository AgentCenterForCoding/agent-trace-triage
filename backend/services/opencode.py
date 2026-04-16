"""OpenCode CLI integration service.

Calls `opencode run --format json` to invoke the agent-trace-triage Skill,
parses JSON Lines output, and yields SSE-compatible progress/result events.
"""

import asyncio
import json
import os
import re
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
SKILL_DIR = PROJECT_ROOT / "skills" / "agent-trace-triage"
SAMPLE_TRACES_DIR = PROJECT_ROOT / "sample_traces"


def _find_opencode() -> str:
    found = shutil.which("opencode")
    if found:
        return found
    npm_global = Path(os.environ.get("APPDATA", "")) / "npm" / "opencode.cmd"
    if npm_global.exists():
        return str(npm_global)
    return "opencode"


def _build_prompt(trace_json: str, enable_llm: bool = True) -> str:
    llm_instruction = ""
    if not enable_llm:
        llm_instruction = "请只使用 L1 规则归因，不要调用 LLM 进行 L2 深度分析。"

    return (
        "请使用 agent-trace-triage skill 分析以下 OTLP JSON trace。"
        f"{llm_instruction}"
        "输出归因结果，必须包含一个 ```json 代码块，字段包括："
        "primary_owner, co_responsible, confidence, fault_span, fault_chain, "
        "root_cause, action_items, source, reasoning。\n\n"
        f"Trace 内容：\n{trace_json}"
    )


def _extract_triage_result(full_text: str) -> dict | None:
    """Extract triage JSON from concatenated text events."""
    match = re.search(r"```json\s*(.*?)\s*```", full_text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict) and "primary_owner" in result:
                return result
        except json.JSONDecodeError:
            pass
    return None


def _classify_event(event: dict) -> dict | None:
    """Convert an opencode JSON Lines event into an SSE-friendly dict."""
    event_type = event.get("type")

    if event_type == "step_start":
        return {"type": "progress", "stage": "thinking", "message": "Agent 开始分析..."}

    if event_type == "tool_use":
        tool = event.get("part", {}).get("tool", "")
        state = event.get("part", {}).get("state", {})
        status = state.get("status", "")
        if status == "completed":
            return {"type": "progress", "stage": "tool", "message": f"读取 {tool}..."}

    if event_type == "text":
        text = event.get("part", {}).get("text", "")
        if "Layer 1" in text or "直接归因" in text or "L1" in text:
            return {"type": "progress", "stage": "l1_rules", "message": "L1 规则归因中..."}
        if "Layer 2" in text or "LLM" in text or "L2" in text:
            return {"type": "progress", "stage": "l2_llm", "message": "L2 LLM 深度归因中..."}
        if "primary_owner" in text:
            return {"type": "progress", "stage": "result", "message": "归因完成，整理结果..."}

    if event_type == "step_finish":
        reason = event.get("part", {}).get("reason", "")
        tokens = event.get("part", {}).get("tokens", {})
        return {
            "type": "progress",
            "stage": "step_done",
            "message": f"步骤完成 ({reason})",
            "tokens": tokens,
        }

    return None


async def run_triage(
    trace_json: str, enable_llm: bool = True
) -> AsyncGenerator[dict, None]:
    """Run triage via opencode CLI, yielding SSE events.

    Yields:
        {"type": "progress", "stage": str, "message": str}
        {"type": "result", "data": dict}  -- the final TriageResult
        {"type": "error", "message": str}  -- on failure
    """
    import tempfile as _tempfile

    yield {"type": "progress", "stage": "start", "message": "开始归因分析..."}

    prompt_path = None
    stdin_fh = None
    try:
        prompt = _build_prompt(trace_json, enable_llm=enable_llm)
        opencode_bin = _find_opencode()

        # Write prompt to temp file and redirect stdin to avoid Windows
        # command-line argument mangling of embedded JSON quotes/brackets.
        fd, prompt_path = _tempfile.mkstemp(suffix=".txt")
        os.write(fd, prompt.encode("utf-8"))
        os.close(fd)

        stdin_fh = open(prompt_path, "rb")
        proc = await asyncio.create_subprocess_exec(
            opencode_bin, "run", "--format", "json",
            stdin=stdin_fh,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(PROJECT_ROOT),
        )
        stdin_fh.close()
        stdin_fh = None

        all_texts: list[str] = []
        last_stage: str | None = None

        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "text":
                text = event.get("part", {}).get("text", "")
                all_texts.append(text)

            sse_event = _classify_event(event)
            if sse_event and sse_event.get("stage") != last_stage:
                last_stage = sse_event.get("stage")
                yield sse_event

        await proc.wait()

        if proc.returncode != 0:
            stderr = ""
            if proc.stderr:
                stderr = (await proc.stderr.read()).decode("utf-8", errors="replace")
            yield {
                "type": "error",
                "message": f"opencode 进程退出码 {proc.returncode}: {stderr[:500]}",
            }
            return

        full_text = "".join(all_texts)
        result = _extract_triage_result(full_text)

        if result:
            yield {"type": "result", "data": result}
        else:
            yield {
                "type": "error",
                "message": "无法从 Skill 输出中提取归因 JSON",
                "raw_text": full_text[:2000],
            }

    except FileNotFoundError:
        yield {"type": "error", "message": "opencode 命令未找到，请确认已安装"}
    except Exception as e:
        yield {"type": "error", "message": f"归因过程异常: {type(e).__name__}: {e}"}
    finally:
        if stdin_fh and not stdin_fh.closed:
            stdin_fh.close()
        if prompt_path:
            try:
                Path(prompt_path).unlink(missing_ok=True)
            except OSError:
                pass


def list_samples() -> list[dict]:
    """List available sample trace files."""
    samples = []
    for f in sorted(SAMPLE_TRACES_DIR.glob("*.json")):
        samples.append({"filename": f.name, "size_bytes": f.stat().st_size})
    return samples


def read_sample(filename: str) -> str | None:
    """Read a sample trace file by name. Returns None if not found."""
    path = SAMPLE_TRACES_DIR / filename
    if not path.exists() or not path.is_file():
        return None
    if ".." in filename or "/" in filename or "\\" in filename:
        return None
    return path.read_text(encoding="utf-8")
