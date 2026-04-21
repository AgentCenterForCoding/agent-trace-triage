"""SOP HTTP endpoints (Phase 0: only retrieve)."""

from fastapi import APIRouter, HTTPException, Query

from sop import registry
from sop.registry import _serialize

router = APIRouter()


def _sop_to_response(sop) -> dict:
    return {
        "meta": sop.meta.model_dump(),
        "body": _serialize(sop),
    }


@router.get("/sops/retrieve")
async def retrieve_sops(
    user_id: str = Query(..., min_length=1),
    query: str | None = Query(None),
    k: int = Query(3, ge=1, le=10),
    include_disabled: bool = Query(False),
):
    try:
        sops = registry.retrieve(
            user_id=user_id,
            query=query,
            k=k,
            include_disabled=include_disabled,
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="invalid user_id")
    return [_sop_to_response(s) for s in sops]
