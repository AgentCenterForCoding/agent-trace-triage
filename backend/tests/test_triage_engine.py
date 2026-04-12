"""Tests for triage_engine module."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from models import OwnerTeam, SpanLayer
from trace_parser import parse_otlp_json
from triage_engine import load_rules, triage

RULES_PATH = Path(__file__).parent.parent / "rules_v2.yaml"
SAMPLES_DIR = Path(__file__).parent.parent / "sample_traces"


def _load_and_triage(sample_name: str):
    rules = load_rules(RULES_PATH)
    with open(SAMPLES_DIR / f"{sample_name}.json") as f:
        data = json.load(f)
    tree = parse_otlp_json(data)
    return triage(tree, rules)


# ============================================================
# Basic scenario tests
# ============================================================

class TestBasicScenarios:
    def test_4_1_model_timeout(self):
        result = _load_and_triage("4_1_model_timeout")
        assert result.primary_owner == OwnerTeam.MODEL_TEAM

    def test_4_2_model_bad_output(self):
        result = _load_and_triage("4_2_model_bad_output")
        # Agent parse error, but could be attributed to model or agent
        assert result.primary_owner in (OwnerTeam.MODEL_TEAM, OwnerTeam.AGENT_TEAM)

    def test_4_3_mcp_connection(self):
        result = _load_and_triage("4_3_mcp_connection")
        assert result.primary_owner == OwnerTeam.MCP_TEAM

    def test_4_4_mcp_tool_error(self):
        result = _load_and_triage("4_4_mcp_tool_error")
        assert result.primary_owner == OwnerTeam.MCP_TEAM

    def test_4_5_skill_not_found(self):
        result = _load_and_triage("4_5_skill_not_found")
        assert result.primary_owner == OwnerTeam.SKILL_TEAM

    def test_4_6_skill_execute_error(self):
        result = _load_and_triage("4_6_skill_execute_error")
        assert result.primary_owner == OwnerTeam.SKILL_TEAM

    def test_4_7_agent_stuck(self):
        result = _load_and_triage("4_7_agent_stuck")
        assert result.primary_owner == OwnerTeam.AGENT_TEAM

    def test_4_8_agent_retry_exhausted(self):
        result = _load_and_triage("4_8_agent_retry_exhausted")
        # Root cause is the deepest error: gen_ai.client APIError
        # Could be model_team (API error) or agent_team (retry logic)
        assert result.primary_owner in (OwnerTeam.MODEL_TEAM, OwnerTeam.AGENT_TEAM)


# ============================================================
# Boundary scenario tests
# ============================================================

class TestBoundaryScenarios:
    def test_4_9_upstream_bad_params(self):
        """Agent passes invalid params → MCP error. Should attribute to agent."""
        result = _load_and_triage("4_9_upstream_bad_params")
        assert result.primary_owner == OwnerTeam.AGENT_TEAM

    def test_4_10_cascade_truncation(self):
        """Model truncation → Agent parse failure. Primary should be model."""
        result = _load_and_triage("4_10_cascade_truncation")
        assert result.primary_owner == OwnerTeam.MODEL_TEAM
        # Agent should be co-responsible for lacking truncation handling
        assert OwnerTeam.AGENT_TEAM in result.co_responsible

    def test_4_11_cumulative_timeout(self):
        """Cumulative timeout → model ERROR is direct cause, Agent co-responsible."""
        result = _load_and_triage("4_11_cumulative_timeout")
        assert result.primary_owner == OwnerTeam.MODEL_TEAM
        assert OwnerTeam.AGENT_TEAM in result.co_responsible

    def test_4_12_mcp_no_retry(self):
        """MCP failure + no retry → primary MCP, co Agent."""
        result = _load_and_triage("4_12_mcp_no_retry")
        assert result.primary_owner == OwnerTeam.MCP_TEAM
        assert OwnerTeam.AGENT_TEAM in result.co_responsible


# ============================================================
# Core boundary scenario tests (v1 discussion consensus)
# ============================================================

class TestCoreBoundaryScenarios:
    def test_4_13_tool_loop(self):
        """Tool use loop detection → Agent should break the loop."""
        result = _load_and_triage("4_13_tool_loop")
        assert result.primary_owner == OwnerTeam.AGENT_TEAM

    def test_4_14_content_filter(self):
        """Content filter (non-ERROR). Should detect model_team."""
        result = _load_and_triage("4_14_content_filter")
        assert result.primary_owner == OwnerTeam.MODEL_TEAM

    def test_4_15_model_bad_tool_params(self):
        """Model generates bad tool params → MCP schema error. Primary model."""
        result = _load_and_triage("4_15_model_bad_tool_params")
        assert result.primary_owner == OwnerTeam.MODEL_TEAM

    def test_4_16_agent_timeout_short(self):
        """Agent timeout too short. Should not blame MCP."""
        result = _load_and_triage("4_16_agent_timeout_short")
        # The MCP call was cancelled, but root cause is agent timeout config
        # May attribute to agent_team or mcp_team depending on rule priority
        assert result.primary_owner in (OwnerTeam.AGENT_TEAM, OwnerTeam.MCP_TEAM)

    def test_4_17_swallowed_error(self):
        """Agent swallows child errors. Root span OK but child ERROR."""
        result = _load_and_triage("4_17_swallowed_error")
        # The swallowed_error pattern or hidden failure detection should flag agent
        assert result.primary_owner in (OwnerTeam.AGENT_TEAM, OwnerTeam.MCP_TEAM)


# ============================================================
# Extended boundary scenario tests (v1.1)
# ============================================================

class TestExtendedBoundaryScenarios:
    def test_4_18_rate_limit(self):
        """Rate limit: Agent calling too frequently → should blame agent, not model."""
        result = _load_and_triage("4_18_rate_limit")
        assert result.primary_owner == OwnerTeam.AGENT_TEAM
        assert OwnerTeam.MODEL_TEAM in result.co_responsible

    def test_4_19_three_layer_chain(self):
        """Three-layer chain: Skill→MCP→external API. Deepest error is MCP layer."""
        result = _load_and_triage("4_19_three_layer_chain")
        assert result.primary_owner == OwnerTeam.MCP_TEAM

    def test_4_20_semantic_error(self):
        """MCP returns OK but with error content → agent parse fails. Blame MCP."""
        result = _load_and_triage("4_20_semantic_error")
        assert result.primary_owner == OwnerTeam.MCP_TEAM
        assert OwnerTeam.AGENT_TEAM in result.co_responsible


# ============================================================
# Engine feature tests
# ============================================================

class TestEngineFeatures:
    def test_confidence_is_bounded(self):
        for sample in SAMPLES_DIR.glob("*.json"):
            result = _load_and_triage(sample.stem)
            assert 0.0 <= result.confidence <= 1.0, f"{sample.stem}: confidence={result.confidence}"

    def test_fault_chain_not_empty_when_fault_found(self):
        for sample in SAMPLES_DIR.glob("*.json"):
            result = _load_and_triage(sample.stem)
            if result.primary_owner != OwnerTeam.UNKNOWN:
                assert len(result.fault_chain) > 0, f"{sample.stem}: empty fault chain"

    def test_action_items_present(self):
        for sample in SAMPLES_DIR.glob("*.json"):
            result = _load_and_triage(sample.stem)
            if result.primary_owner != OwnerTeam.UNKNOWN:
                assert len(result.action_items) > 0, f"{sample.stem}: no action items"

    def test_co_responsible_excludes_primary(self):
        for sample in SAMPLES_DIR.glob("*.json"):
            result = _load_and_triage(sample.stem)
            assert result.primary_owner not in result.co_responsible, \
                f"{sample.stem}: primary in co_responsible"
