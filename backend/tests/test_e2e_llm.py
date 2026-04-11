"""
End-to-end tests for L2 LLM inference with real API calls.

These tests require a live LLM API connection and are skipped by default.
Run with: pytest tests/test_e2e_llm.py -v --run-e2e

Environment:
  ANTHROPIC_BASE_URL  (default: https://coding.dashscope.aliyuncs.com/apps/anthropic)
  ANTHROPIC_MODEL     (default: qwen3.6-plus)
  ANTHROPIC_AUTH_TOKEN (required for e2e tests)
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import OwnerTeam, TriageSource
from router import LLMConfig
from trace_parser import parse_otlp_json
from triage_engine import load_rules, triage_hybrid

SAMPLE_DIR = Path(__file__).parent.parent / "sample_traces"
RULES_PATH = Path(__file__).parent.parent / "rules.yaml"


def _get_llm_config() -> LLMConfig:
    """Get LLM config from environment."""
    api_key = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    return LLMConfig(
        enabled=True,
        base_url=os.environ.get("ANTHROPIC_BASE_URL",
                                "https://coding.dashscope.aliyuncs.com/apps/anthropic"),
        model=os.environ.get("ANTHROPIC_MODEL", "qwen3.6-plus"),
        threshold=0.8,
        api_key=api_key,
        timeout=120,
    )


def _load_and_triage(sample_name: str):
    """Load a sample trace and run hybrid triage."""
    rules = load_rules(RULES_PATH)
    with open(SAMPLE_DIR / f"{sample_name}.json") as f:
        data = json.load(f)
    tree = parse_otlp_json(data)
    config = _get_llm_config()
    return triage_hybrid(tree, rules, config)


# ============================================================
# E2E Tests: Low confidence trace → L2 LLM → Correct attribution
# ============================================================

@pytest.mark.e2e
class TestE2ELLM:
    """End-to-end tests that call real LLM API for low-confidence traces."""

    def test_c1_multi_layer_error_triggers_l2(self):
        """C1: Multiple layers with errors. L1 low confidence → L2 should provide attribution."""
        result = _load_and_triage("c1_multi_layer_error")
        assert result.source == TriageSource.LLM
        assert result.primary_owner != OwnerTeam.UNKNOWN
        assert result.confidence > 0
        assert result.reasoning is not None
        assert len(result.reasoning) > 0

    def test_c3_semantic_error_unknown_from_l1(self):
        """C3: Semantic error. L1 returns UNKNOWN → L2 must provide attribution."""
        result = _load_and_triage("c3_semantic_error")
        assert result.source == TriageSource.LLM
        assert result.primary_owner != OwnerTeam.UNKNOWN
        assert len(result.action_items) > 0

    def test_c6_model_hallucination_chain(self):
        """C6: Model hallucination chain. L1 low conf → L2 should reason about causality."""
        result = _load_and_triage("c6_model_hallucination_chain")
        assert result.source == TriageSource.LLM
        assert result.primary_owner in (OwnerTeam.MODEL_TEAM, OwnerTeam.AGENT_TEAM)
        assert result.reasoning is not None

    def test_c8_recursive_agent_failure(self):
        """C8: Recursive agent failure. L2 should trace through recursion."""
        result = _load_and_triage("c8_recursive_agent_failure")
        assert result.source == TriageSource.LLM
        assert result.primary_owner != OwnerTeam.UNKNOWN
        assert result.confidence >= 0.5

    def test_l2_result_structure_completeness(self):
        """Verify L2 results have all required fields populated."""
        result = _load_and_triage("c10_mixed_error_types")
        assert result.source == TriageSource.LLM
        assert result.primary_owner != OwnerTeam.UNKNOWN
        assert 0.0 <= result.confidence <= 1.0
        assert result.root_cause and len(result.root_cause) > 0
        assert result.reasoning and len(result.reasoning) > 0
        assert len(result.action_items) > 0
        # co_responsible should not contain primary
        assert result.primary_owner not in result.co_responsible
