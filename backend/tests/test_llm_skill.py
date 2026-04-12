"""Unit tests for llm_skill.py - L2 LLM inference module."""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock

from models import (
    OTelSpan,
    OwnerTeam,
    SpanLayer,
    SpanStatus,
    SpanTree,
    TriageResult,
    TriageSource,
)
from router import LLMConfig
from llm_skill import (
    build_input,
    parse_output,
    build_triage_result,
    invoke_llm,
    l2_inference,
    LLMInvocationError,
    LLMOutputParseError,
    SYSTEM_PROMPT,
)


class TestBuildInput:
    """Tests for build_input function."""

    def _make_span(
        self,
        span_id: str,
        name: str,
        status: SpanStatus = SpanStatus.OK,
        parent_span_id: str = None,
        attributes: dict = None,
    ) -> OTelSpan:
        """Helper to create a span."""
        return OTelSpan(
            trace_id="test_trace",
            span_id=span_id,
            parent_span_id=parent_span_id,
            name=name,
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            status=status,
            status_message="Test message" if status == SpanStatus.ERROR else None,
            attributes=attributes or {},
        )

    def _make_tree(self, spans: list[OTelSpan]) -> SpanTree:
        """Helper to create a span tree."""
        spans_dict = {s.span_id: s for s in spans}
        root_spans = [s.span_id for s in spans if s.parent_span_id is None]
        return SpanTree(
            trace_id="test_trace",
            spans=spans_dict,
            root_spans=root_spans,
        )

    def _make_l1_result(self) -> TriageResult:
        """Helper to create L1 result."""
        return TriageResult(
            primary_owner=OwnerTeam.MODEL_TEAM,
            co_responsible=[OwnerTeam.AGENT_TEAM],
            confidence=0.6,
            root_cause="Model timeout",
            source=TriageSource.RULES,
        )

    def test_trace_summary_fields(self):
        """Test trace summary structure."""
        spans = [
            self._make_span("s1", "turn"),
            self._make_span("s2", "model_inference", parent_span_id="s1"),
        ]
        tree = self._make_tree(spans)
        l1 = self._make_l1_result()

        result = build_input(tree, [], l1)

        assert "trace_summary" in result
        summary = result["trace_summary"]
        assert summary["total_spans"] == 2
        assert "turn" in summary["root_span_names"]
        assert isinstance(summary["layers"], list)

    def test_error_chain_structure(self):
        """Test error chain structure in input."""
        error_span = self._make_span(
            "s1", "model_inference",
            status=SpanStatus.ERROR,
            attributes={"model": "claude-3-opus", "error_type": "TimeoutError"},
        )
        error_span.depth = 1

        tree = self._make_tree([error_span])
        l1 = self._make_l1_result()
        l1.fault_chain = [error_span]

        result = build_input(tree, [error_span], l1)

        assert "error_chain" in result
        assert len(result["error_chain"]) == 1
        chain_item = result["error_chain"][0]
        assert chain_item["span_name"] == "model_inference"
        assert chain_item["status"] == "ERROR"
        assert "key_attributes" in chain_item

    def test_rule_engine_result_structure(self):
        """Test L1 result summary in input."""
        tree = self._make_tree([self._make_span("s1", "turn")])
        l1 = self._make_l1_result()

        result = build_input(tree, [], l1)

        assert "rule_engine_result" in result
        l1_summary = result["rule_engine_result"]
        assert l1_summary["primary_owner"] == "model_team"
        assert l1_summary["confidence"] == 0.6
        assert "agent_team" in l1_summary["co_responsible"]

    def test_key_attributes_extraction(self):
        """Test extraction of key attributes."""
        span = self._make_span(
            "s1", "tool_call",
            attributes={
                "tool_type": "mcp",
                "function_name": "read_file",
                "success": False,
                "error_type": "ConnectionError",
                "irrelevant_attr": "should_be_ignored",
            },
        )

        tree = self._make_tree([span])
        l1 = self._make_l1_result()

        result = build_input(tree, [span], l1)

        chain_item = result["error_chain"][0]
        attrs = chain_item["key_attributes"]
        assert attrs["tool_type"] == "mcp"
        assert attrs["function_name"] == "read_file"
        assert "irrelevant_attr" not in attrs


class TestParseOutput:
    """Tests for parse_output function."""

    def test_valid_json(self):
        """Test parsing valid JSON response."""
        response = json.dumps({
            "primary_owner": "model_team",
            "co_responsible": ["agent_team"],
            "confidence": 0.85,
            "root_cause": "Model API timeout",
            "reasoning": "The model inference span failed first",
            "action_items": ["[model_team] Add retry logic"],
        })

        result = parse_output(response)

        assert result["primary_owner"] == "model_team"
        assert result["confidence"] == 0.85
        assert "reasoning" in result

    def test_json_in_markdown_code_block(self):
        """Test extracting JSON from markdown code block."""
        response = """```json
{
  "primary_owner": "mcp_team",
  "confidence": 0.9,
  "root_cause": "MCP connection failed"
}
```"""

        result = parse_output(response)
        assert result["primary_owner"] == "mcp_team"

    def test_invalid_json_raises_error(self):
        """Test that invalid JSON raises LLMOutputParseError."""
        response = "This is not valid JSON"

        with pytest.raises(LLMOutputParseError) as exc_info:
            parse_output(response)
        assert "Invalid JSON" in str(exc_info.value)

    def test_missing_required_field_raises_error(self):
        """Test that missing required field raises error."""
        response = json.dumps({
            "primary_owner": "model_team",
            # Missing confidence and root_cause
        })

        with pytest.raises(LLMOutputParseError) as exc_info:
            parse_output(response)
        assert "Missing required field" in str(exc_info.value)

    def test_invalid_primary_owner_raises_error(self):
        """Test that invalid owner value raises error."""
        response = json.dumps({
            "primary_owner": "invalid_team",
            "confidence": 0.8,
            "root_cause": "Test",
        })

        with pytest.raises(LLMOutputParseError) as exc_info:
            parse_output(response)
        assert "Invalid primary_owner" in str(exc_info.value)

    def test_confidence_out_of_range_raises_error(self):
        """Test that confidence > 1.0 raises error."""
        response = json.dumps({
            "primary_owner": "model_team",
            "confidence": 1.5,
            "root_cause": "Test",
        })

        with pytest.raises(LLMOutputParseError) as exc_info:
            parse_output(response)
        assert "Confidence out of range" in str(exc_info.value)

    def test_confidence_negative_raises_error(self):
        """Test that negative confidence raises error."""
        response = json.dumps({
            "primary_owner": "model_team",
            "confidence": -0.1,
            "root_cause": "Test",
        })

        with pytest.raises(LLMOutputParseError) as exc_info:
            parse_output(response)
        assert "Confidence out of range" in str(exc_info.value)

    def test_valid_owner_values(self):
        """Test all valid owner values are accepted."""
        valid_owners = ["agent_team", "model_team", "mcp_team", "skill_team", "user_interaction", "unknown"]

        for owner in valid_owners:
            response = json.dumps({
                "primary_owner": owner,
                "confidence": 0.8,
                "root_cause": "Test",
            })
            result = parse_output(response)
            assert result["primary_owner"] == owner

    @pytest.mark.parametrize("alias", ["none", "null", "n/a", "na", "nan", "", "NONE", "  none  "])
    def test_unknown_aliases_normalized(self, alias):
        """LLMs using 'none'/'null'/'n/a'/'' for primary_owner should be
        normalized to 'unknown' instead of rejected.

        Regression for c3_semantic_error where qwen3.6-plus returned
        primary_owner='none', triggering a silent fallback to L1.
        """
        response = json.dumps({
            "primary_owner": alias,
            "confidence": 0.0,
            "root_cause": "no fault indicators found",
        })
        result = parse_output(response)
        assert result["primary_owner"] == "unknown"

    def test_null_json_primary_owner_normalized(self):
        """JSON null (Python None) for primary_owner → 'unknown'."""
        response = '{"primary_owner": null, "confidence": 0.0, "root_cause": "x"}'
        result = parse_output(response)
        assert result["primary_owner"] == "unknown"

    def test_co_responsible_aliases_normalized(self):
        """Alias strings inside co_responsible should also be normalized."""
        response = json.dumps({
            "primary_owner": "model_team",
            "co_responsible": ["agent_team", "none", None, "null"],
            "confidence": 0.8,
            "root_cause": "Test",
        })
        result = parse_output(response)
        # The three alias variants all collapse to "unknown"; the real team stays.
        assert result["co_responsible"].count("unknown") == 3
        assert "agent_team" in result["co_responsible"]


class TestBuildTriageResult:
    """Tests for build_triage_result function."""

    def _make_l1_result(self) -> TriageResult:
        """Helper to create L1 result with fault chain."""
        fault_span = OTelSpan(
            trace_id="test",
            span_id="fault_span",
            name="model_inference",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            status=SpanStatus.ERROR,
        )
        return TriageResult(
            primary_owner=OwnerTeam.UNKNOWN,
            confidence=0.3,
            root_cause="Unknown error",
            fault_span=fault_span,
            fault_chain=[fault_span],
            source=TriageSource.RULES,
        )

    def test_owner_mapping(self):
        """Test primary_owner string to enum mapping."""
        parsed = {
            "primary_owner": "model_team",
            "confidence": 0.9,
            "root_cause": "Model failed",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.primary_owner == OwnerTeam.MODEL_TEAM
        assert result.source == TriageSource.LLM

    def test_co_responsible_mapping(self):
        """Test co_responsible list mapping."""
        parsed = {
            "primary_owner": "model_team",
            "co_responsible": ["agent_team", "mcp_team"],
            "confidence": 0.8,
            "root_cause": "Test",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert OwnerTeam.AGENT_TEAM in result.co_responsible
        assert OwnerTeam.MCP_TEAM in result.co_responsible

    def test_primary_excluded_from_co_responsible(self):
        """Test that primary owner is excluded from co_responsible."""
        parsed = {
            "primary_owner": "model_team",
            "co_responsible": ["model_team", "agent_team"],  # model_team should be excluded
            "confidence": 0.8,
            "root_cause": "Test",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert OwnerTeam.MODEL_TEAM not in result.co_responsible
        assert OwnerTeam.AGENT_TEAM in result.co_responsible

    def test_preserves_l1_fault_chain(self):
        """Test that L1's fault_span and fault_chain are preserved."""
        parsed = {
            "primary_owner": "model_team",
            "confidence": 0.9,
            "root_cause": "Model failed",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.fault_span == l1.fault_span
        assert result.fault_chain == l1.fault_chain

    def test_reasoning_included(self):
        """Test that reasoning is included in result."""
        parsed = {
            "primary_owner": "model_team",
            "confidence": 0.9,
            "root_cause": "Model failed",
            "reasoning": "Step 1: Found error. Step 2: Traced to model.",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.reasoning == "Step 1: Found error. Step 2: Traced to model."

    def test_action_items_included(self):
        """Test that action_items are included."""
        parsed = {
            "primary_owner": "model_team",
            "confidence": 0.9,
            "root_cause": "Model failed",
            "action_items": ["[model_team] Add retry", "[agent_team] Add fallback"],
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert len(result.action_items) == 2

    def test_zero_confidence_with_team_coerced_to_unknown(self):
        """Regression: LLM returns confidence=0 + a specific team → contradictory.

        Coerce to UNKNOWN and stash the original guess in root_cause so the
        user can still see what the LLM was thinking.
        """
        parsed = {
            "primary_owner": "agent_team",
            "co_responsible": ["model_team"],
            "confidence": 0.0,
            "root_cause": "No fault indicators found in trace",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.primary_owner == OwnerTeam.UNKNOWN
        assert result.co_responsible == []
        assert result.confidence == 0.0
        # Original guess should be preserved for debugging.
        assert "agent_team" in result.root_cause
        assert "raw guess" in result.root_cause
        assert "No fault indicators found" in result.root_cause

    def test_near_zero_confidence_with_team_also_coerced(self):
        """Confidence just below epsilon (0.04) is still contradictory."""
        parsed = {
            "primary_owner": "mcp_team",
            "confidence": 0.04,
            "root_cause": "maybe mcp",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.primary_owner == OwnerTeam.UNKNOWN
        assert "mcp_team" in result.root_cause

    def test_low_but_nonzero_confidence_preserved(self):
        """Low-but-consistent confidence (e.g., 0.3) is a legitimate weak guess,
        not contradictory. Must NOT be coerced."""
        parsed = {
            "primary_owner": "model_team",
            "co_responsible": ["agent_team"],
            "confidence": 0.3,
            "root_cause": "Weak signal",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.primary_owner == OwnerTeam.MODEL_TEAM
        assert result.confidence == 0.3
        assert result.root_cause == "Weak signal"  # unmutated

    def test_zero_confidence_with_unknown_owner_unchanged(self):
        """LLM saying '{unknown, 0.0}' is self-consistent — don't touch it."""
        parsed = {
            "primary_owner": "unknown",
            "confidence": 0.0,
            "root_cause": "Cannot determine",
        }
        l1 = self._make_l1_result()

        result = build_triage_result(parsed, l1)

        assert result.primary_owner == OwnerTeam.UNKNOWN
        assert result.root_cause == "Cannot determine"  # NOT mutated


class TestInvokeLLM:
    """Tests for invoke_llm function with mocked API."""

    @patch("llm_skill.Anthropic")
    def test_successful_invocation(self, mock_anthropic_class):
        """Test successful LLM API call."""
        # Setup mock
        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"primary_owner": "model_team"}')]
        mock_client.messages.create.return_value = mock_response

        config = LLMConfig(
            enabled=True,
            api_key="sk-test",
            model="test-model",
        )

        result = invoke_llm({"test": "data"}, config)

        assert result == '{"primary_owner": "model_team"}'
        mock_client.messages.create.assert_called_once()

    @patch("llm_skill.Anthropic")
    def test_api_timeout_raises_error(self, mock_anthropic_class):
        """Test that API timeout raises LLMInvocationError."""
        from anthropic import APITimeoutError

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = APITimeoutError(request=MagicMock())

        config = LLMConfig(enabled=True, api_key="sk-test")

        with pytest.raises(LLMInvocationError) as exc_info:
            invoke_llm({}, config)
        assert "timeout" in str(exc_info.value).lower()

    @patch("llm_skill.Anthropic")
    def test_api_error_raises_error(self, mock_anthropic_class):
        """Test that API error raises LLMInvocationError."""
        from anthropic import APIError

        mock_client = MagicMock()
        mock_anthropic_class.return_value = mock_client
        mock_client.messages.create.side_effect = APIError(
            message="Rate limit exceeded",
            request=MagicMock(),
            body=None,
        )

        config = LLMConfig(enabled=True, api_key="sk-test")

        with pytest.raises(LLMInvocationError) as exc_info:
            invoke_llm({}, config)
        assert "API error" in str(exc_info.value)


class TestL2Inference:
    """Tests for l2_inference end-to-end function."""

    def _make_tree_and_l1(self):
        """Helper to create test tree and L1 result."""
        span = OTelSpan(
            trace_id="test",
            span_id="s1",
            name="model_inference",
            start_time_unix_nano=1700000000000000000,
            end_time_unix_nano=1700000001000000000,
            status=SpanStatus.ERROR,
            status_message="Timeout",
        )
        tree = SpanTree(
            trace_id="test",
            spans={"s1": span},
            root_spans=["s1"],
        )
        l1 = TriageResult(
            primary_owner=OwnerTeam.UNKNOWN,
            confidence=0.3,
            root_cause="Unknown",
            fault_span=span,
            fault_chain=[span],
            source=TriageSource.RULES,
        )
        return tree, l1

    @patch("llm_skill.invoke_llm")
    def test_successful_l2_inference(self, mock_invoke):
        """Test successful L2 inference flow."""
        mock_invoke.return_value = json.dumps({
            "primary_owner": "model_team",
            "confidence": 0.9,
            "root_cause": "Model API timeout",
            "reasoning": "Traced timeout to model layer",
        })

        tree, l1 = self._make_tree_and_l1()
        config = LLMConfig(enabled=True, api_key="sk-test")

        result = l2_inference(tree, l1, config)

        assert result.primary_owner == OwnerTeam.MODEL_TEAM
        assert result.source == TriageSource.LLM
        assert result.confidence == 0.9

    @patch("llm_skill.invoke_llm")
    def test_invocation_error_falls_back_to_l1(self, mock_invoke):
        """Test fallback to L1 on invocation error."""
        mock_invoke.side_effect = LLMInvocationError("API failed")

        tree, l1 = self._make_tree_and_l1()
        config = LLMConfig(enabled=True, api_key="sk-test")

        result = l2_inference(tree, l1, config)

        # Should return L1 result unchanged
        assert result.primary_owner == OwnerTeam.UNKNOWN
        assert result.source == TriageSource.RULES
        assert result.confidence == 0.3

    @patch("llm_skill.invoke_llm")
    def test_parse_error_falls_back_to_l1(self, mock_invoke):
        """Test fallback to L1 on parse error."""
        mock_invoke.return_value = "invalid json response"

        tree, l1 = self._make_tree_and_l1()
        config = LLMConfig(enabled=True, api_key="sk-test")

        result = l2_inference(tree, l1, config)

        # Should return L1 result unchanged
        assert result.primary_owner == OwnerTeam.UNKNOWN
        assert result.source == TriageSource.RULES


class TestSystemPrompt:
    """Tests for SYSTEM_PROMPT content."""

    def test_prompt_contains_four_layer_model(self):
        """Test prompt describes four-layer architecture."""
        assert "四层架构模型" in SYSTEM_PROMPT
        assert "agent_team" in SYSTEM_PROMPT
        assert "model_team" in SYSTEM_PROMPT
        assert "mcp_team" in SYSTEM_PROMPT
        assert "skill_team" in SYSTEM_PROMPT

    def test_prompt_contains_three_layer_algorithm(self):
        """Test prompt describes three-layer attribution algorithm."""
        assert "三层归因算法" in SYSTEM_PROMPT
        assert "直接归因" in SYSTEM_PROMPT
        assert "上游传播" in SYSTEM_PROMPT
        assert "容错分析" in SYSTEM_PROMPT

    def test_prompt_specifies_json_output(self):
        """Test prompt requires JSON output format."""
        assert "JSON" in SYSTEM_PROMPT
        assert "primary_owner" in SYSTEM_PROMPT
        assert "confidence" in SYSTEM_PROMPT
        assert "中文" in SYSTEM_PROMPT
