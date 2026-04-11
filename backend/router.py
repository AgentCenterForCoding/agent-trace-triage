"""Confidence-based router for L1/L2 triage."""

from dataclasses import dataclass
from typing import Optional

from models import TriageResult, OwnerTeam


@dataclass
class LLMConfig:
    """LLM configuration from frontend."""
    enabled: bool = False
    base_url: str = "https://coding.dashscope.aliyuncs.com/apps/anthropic"
    model: str = "qwen3.6-plus"
    threshold: float = 0.8
    api_key: str = ""
    timeout: int = 60  # Increased for DashScope API latency


def should_invoke_l2(l1_result: TriageResult, config: LLMConfig) -> bool:
    """
    Decide whether to invoke L2 LLM inference.

    Triggers L2 when:
    1. L2 is enabled in config
    2. API key is provided
    3. L1 confidence < threshold OR L1 returned UNKNOWN owner
    """
    if not config.enabled:
        return False

    if not config.api_key:
        return False

    # Always trigger L2 if L1 returned UNKNOWN
    if l1_result.primary_owner == OwnerTeam.UNKNOWN:
        return True

    # Trigger L2 if confidence below threshold
    if l1_result.confidence < config.threshold:
        return True

    return False


def parse_llm_config_from_headers(headers: dict) -> Optional[LLMConfig]:
    """Parse LLM config from request headers."""
    # Check if LLM is enabled
    enabled = headers.get("x-llm-enabled", "").lower() == "true"
    if not enabled:
        return None

    api_key = headers.get("x-llm-api-key", "")
    if not api_key:
        return None

    return LLMConfig(
        enabled=True,
        base_url=headers.get("x-llm-base-url", LLMConfig.base_url),
        model=headers.get("x-llm-model", LLMConfig.model),
        threshold=float(headers.get("x-llm-threshold", LLMConfig.threshold)),
        api_key=api_key,
        timeout=int(headers.get("x-llm-timeout", LLMConfig.timeout)),
    )
