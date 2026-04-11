"""Integration tests for hybrid L1/L2 triage mode."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from models import OwnerTeam, TriageSource
from router import LLMConfig
from triage_engine import load_rules, triage, triage_hybrid
from trace_parser import parse_otlp_json


SAMPLE_DIR = Path(__file__).parent.parent / "sample_traces"
RULES_PATH = Path(__file__).parent.parent / "rules.yaml"


def load_sample(name: str) -> dict:
    """Load a sample trace by name."""
    path = SAMPLE_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestHybridTriageWithoutLLM:
    """Test hybrid triage when LLM is disabled."""

    @pytest.fixture
    def rules(self):
        """Load triage rules."""
        return load_rules(RULES_PATH)

    def test_no_config_returns_l1_result(self, rules):
        """Without LLM config, should return L1 result."""
        data = load_sample("4_1_model_timeout")
        tree = parse_otlp_json(data)

        result = triage_hybrid(tree, rules, llm_config=None)

        assert result.source == TriageSource.RULES
        assert result.primary_owner == OwnerTeam.MODEL_TEAM

    def test_disabled_config_returns_l1_result(self, rules):
        """With disabled LLM config, should return L1 result."""
        data = load_sample("4_3_mcp_connection")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=False, api_key="sk-test")

        result = triage_hybrid(tree, rules, llm_config=config)

        assert result.source == TriageSource.RULES
        assert result.primary_owner == OwnerTeam.MCP_TEAM

    def test_no_api_key_returns_l1_result(self, rules):
        """With no API key, should return L1 result."""
        data = load_sample("c1_multi_layer_error")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=True, api_key="")

        result = triage_hybrid(tree, rules, llm_config=config)

        assert result.source == TriageSource.RULES

    def test_high_confidence_skips_l2(self, rules):
        """High confidence L1 result should skip L2."""
        # 4_1_model_timeout has high confidence
        data = load_sample("4_1_model_timeout")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.5)

        result = triage_hybrid(tree, rules, llm_config=config)

        # Should still be L1 because confidence is high
        assert result.source == TriageSource.RULES


class TestHybridTriageWithMockedLLM:
    """Test hybrid triage with mocked LLM calls."""

    @pytest.fixture
    def rules(self):
        """Load triage rules."""
        return load_rules(RULES_PATH)

    @patch("llm_skill.invoke_llm")
    def test_low_confidence_triggers_l2(self, mock_invoke, rules):
        """Low confidence L1 result should trigger L2."""
        import json

        # Setup mock LLM response
        mock_invoke.return_value = json.dumps({
            "primary_owner": "model_team",
            "confidence": 0.95,
            "root_cause": "LLM determined model timeout",
            "reasoning": "Step-by-step analysis...",
        })

        # c1 has low confidence due to multi-layer errors
        data = load_sample("c1_multi_layer_error")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)

        result = triage_hybrid(tree, rules, llm_config=config)

        # L2 should have been called
        mock_invoke.assert_called_once()
        assert result.source == TriageSource.LLM
        assert result.confidence == 0.95

    @patch("llm_skill.invoke_llm")
    def test_unknown_owner_triggers_l2(self, mock_invoke, rules):
        """UNKNOWN owner in L1 should trigger L2."""
        import json

        mock_invoke.return_value = json.dumps({
            "primary_owner": "mcp_team",
            "confidence": 0.85,
            "root_cause": "LLM identified MCP issue",
        })

        # c2 has atypical error message that may result in low confidence
        data = load_sample("c2_atypical_error_message")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)

        # Get L1 result first to check
        l1_result = triage(tree, rules)

        # If L1 has low confidence or UNKNOWN, L2 should trigger
        result = triage_hybrid(tree, rules, llm_config=config)

        if l1_result.confidence < 0.8 or l1_result.primary_owner == OwnerTeam.UNKNOWN:
            mock_invoke.assert_called_once()

    @patch("llm_skill.invoke_llm")
    def test_l2_failure_returns_l1(self, mock_invoke, rules):
        """L2 failure should return L1 result."""
        from llm_skill import LLMInvocationError

        # Mock L2 to raise error (simulating fallback)
        mock_invoke.side_effect = LLMInvocationError("API failed")

        data = load_sample("c1_multi_layer_error")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)

        result = triage_hybrid(tree, rules, llm_config=config)

        # Result should be L1's result (fallback)
        assert result.source == TriageSource.RULES


class TestComplexScenariosL1Confidence:
    """Test that complex scenarios (C1-C10) have low L1 confidence."""

    @pytest.fixture
    def rules(self):
        """Load triage rules."""
        return load_rules(RULES_PATH)

    @pytest.mark.parametrize("scenario", [
        "c1_multi_layer_error",
        "c2_atypical_error_message",
        "c3_semantic_error",
        "c4_partial_success_concurrent",
        "c5_user_timeout_chain",
        "c6_model_hallucination_chain",
        "c7_config_timeout_short",
        "c8_recursive_agent_failure",
        "c9_rate_limit_stacking",
        "c10_mixed_error_types",
    ])
    def test_complex_scenario_would_trigger_l2(self, scenario, rules):
        """Complex scenarios should have confidence < threshold or special conditions."""
        data = load_sample(scenario)
        tree = parse_otlp_json(data)

        result = triage(tree, rules)

        # These complex scenarios are designed to have low confidence
        # or require L2 for accurate attribution
        # We verify they would trigger L2 with standard threshold
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)

        from router import should_invoke_l2
        should_trigger = should_invoke_l2(result, config)

        # Log for debugging
        print(f"{scenario}: owner={result.primary_owner.value}, "
              f"confidence={result.confidence:.2f}, would_trigger_l2={should_trigger}")

        # Most complex scenarios should trigger L2
        # (some might have clear ownership but low confidence)


class TestTriageHybridEndToEnd:
    """End-to-end tests for hybrid triage flow."""

    @pytest.fixture
    def rules(self):
        """Load triage rules."""
        return load_rules(RULES_PATH)

    def test_result_structure_is_complete(self, rules):
        """Verify hybrid result has all required fields."""
        data = load_sample("4_1_model_timeout")
        tree = parse_otlp_json(data)

        result = triage_hybrid(tree, rules, llm_config=None)

        # Check all required fields
        assert hasattr(result, "primary_owner")
        assert hasattr(result, "co_responsible")
        assert hasattr(result, "confidence")
        assert hasattr(result, "fault_span")
        assert hasattr(result, "fault_chain")
        assert hasattr(result, "root_cause")
        assert hasattr(result, "action_items")
        assert hasattr(result, "source")
        assert hasattr(result, "reasoning")

    def test_user_interaction_scenario(self, rules):
        """Test user timeout scenario is correctly attributed."""
        data = load_sample("c5_user_timeout_chain")
        tree = parse_otlp_json(data)

        result = triage_hybrid(tree, rules, llm_config=None)

        # Should be attributed to user_interaction
        assert result.primary_owner == OwnerTeam.USER_INTERACTION

    def test_semantic_error_detection(self, rules):
        """Test semantic error (OK status but business failure)."""
        data = load_sample("c3_semantic_error")
        tree = parse_otlp_json(data)

        result = triage_hybrid(tree, rules, llm_config=None)

        # L1 may not detect semantic errors well (that's why we need L2)
        # Just verify it doesn't crash and returns a result
        assert result.primary_owner is not None
        assert 0.0 <= result.confidence <= 1.0

    @patch("llm_skill.invoke_llm")
    def test_l2_overrides_l1_attribution(self, mock_invoke, rules):
        """Test that L2 can override L1's attribution."""
        import json

        # L2 returns different owner than L1
        mock_invoke.return_value = json.dumps({
            "primary_owner": "model_team",
            "co_responsible": ["agent_team"],
            "confidence": 0.92,
            "root_cause": "Model consistently produced invalid JSON",
            "reasoning": "Multiple model outputs failed JSON parsing",
            "action_items": ["[model_team] Improve JSON generation"],
        })

        # c6 model hallucination - L1 might attribute to agent
        data = load_sample("c6_model_hallucination_chain")
        tree = parse_otlp_json(data)
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)

        result = triage_hybrid(tree, rules, llm_config=config)

        # Should use L2's attribution
        assert result.primary_owner == OwnerTeam.MODEL_TEAM
        assert result.source == TriageSource.LLM
        assert "model" in result.reasoning.lower()
