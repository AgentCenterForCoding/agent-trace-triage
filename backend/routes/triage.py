"""
Triage 归因路由

POST /api/v1/triage - SSE 实时归因
POST /api/v1/triage/async - 异步归因（返回 task_id）
GET /api/v1/triage/{task_id} - 查询异步任务结果
"""

import json
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from schemas.triage import (
    TriageRequest,
    TriageResult,
    ProgressEvent,
    AsyncTaskCreate,
    AsyncTaskStatus,
)
from services.opencode import run_triage

router = APIRouter()

# 内存存储异步任务（MVP，重启后丢失）
_async_tasks: dict[str, AsyncTaskStatus] = {}


async def sse_generator(request: TriageRequest) -> AsyncGenerator[str, None]:
    """SSE 事件生成器"""
    try:
        trace_json = json.dumps(request.trace) if isinstance(request.trace, dict) else request.trace

        async for event in run_triage(trace_json, enable_llm=request.enable_llm):
            if event["type"] == "progress":
                yield f"event: progress\ndata: {json.dumps(event)}\n\n"
            elif event["type"] == "result":
                yield f"event: result\ndata: {json.dumps(event['data'])}\n\n"
            elif event["type"] == "error":
                yield f"event: error\ndata: {json.dumps(event)}\n\n"
    except Exception as e:
        yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"


@router.post("/triage")
async def triage_sse(request: TriageRequest):
    """SSE 实时归因接口"""
    return StreamingResponse(
        sse_generator(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@router.post("/triage/async", response_model=AsyncTaskCreate)
async def triage_async(request: TriageRequest):
    """异步归因接口（任务状态在内存中，重启后丢失）"""
    task_id = str(uuid.uuid4())
    _async_tasks[task_id] = AsyncTaskStatus(task_id=task_id, status="pending")

    try:
        trace_json = json.dumps(request.trace) if isinstance(request.trace, dict) else request.trace
        _async_tasks[task_id].status = "processing"

        result = None
        async for event in run_triage(trace_json, enable_llm=request.enable_llm):
            if event["type"] == "result":
                result = event["data"]
                break

        if result:
            _async_tasks[task_id].status = "completed"
            _async_tasks[task_id].result = TriageResult(**result)
        else:
            _async_tasks[task_id].status = "failed"
            _async_tasks[task_id].error = "No result returned"
    except Exception as e:
        _async_tasks[task_id].status = "failed"
        _async_tasks[task_id].error = str(e)

    return AsyncTaskCreate(task_id=task_id, status=_async_tasks[task_id].status)


@router.get("/triage/{task_id}", response_model=AsyncTaskStatus)
async def get_task_status(task_id: str):
    """查询异步任务状态"""
    if task_id not in _async_tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return _async_tasks[task_id]
