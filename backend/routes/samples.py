"""
样本 Trace 路由

GET /api/v1/samples - 获取样本列表
GET /api/v1/samples/{filename} - 获取样本内容
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from schemas.triage import SampleInfo

router = APIRouter()

SAMPLES_DIR = Path(__file__).parent.parent.parent / "sample_traces"


@router.get("/samples", response_model=list[SampleInfo])
async def list_samples():
    """获取样本 Trace 文件列表"""
    if not SAMPLES_DIR.exists():
        return []
    return [
        SampleInfo(filename=f.name, size_bytes=f.stat().st_size)
        for f in sorted(SAMPLES_DIR.glob("*.json"))
    ]


@router.get("/samples/{filename}")
async def get_sample(filename: str):
    """获取样本 Trace 内容"""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    file_path = SAMPLES_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Sample not found")

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)
