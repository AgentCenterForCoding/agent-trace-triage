from pydantic import BaseModel, Field


class FaultSpan(BaseModel):
    span_id: str
    name: str
    status: str
    status_message: str = ""


class TriageResult(BaseModel):
    primary_owner: str
    co_responsible: list[str] = Field(default_factory=list)
    confidence: float
    fault_span: FaultSpan | None = None
    fault_chain: list[dict] = Field(default_factory=list)
    root_cause: str = ""
    action_items: list[str] = Field(default_factory=list)
    source: str | None = None
    reasoning: str | None = None


class ProgressEvent(BaseModel):
    type: str = "progress"
    stage: str
    message: str


class TriageRequest(BaseModel):
    trace: dict | str
    enable_llm: bool = True  # 是否启用 L2 LLM 归因


class SampleInfo(BaseModel):
    filename: str
    size_bytes: int


class AsyncTaskStatus(BaseModel):
    """异步任务状态"""
    task_id: str
    status: str  # pending, processing, completed, failed
    result: TriageResult | None = None
    error: str | None = None


class AsyncTaskCreate(BaseModel):
    """异步任务创建响应"""
    task_id: str
    status: str = "pending"
