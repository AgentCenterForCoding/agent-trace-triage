"""Unit tests for router.py - Confidence-based L1/L2 routing."""

import pytest

from models import OwnerTeam, TriageResult, TriageSource
from router import LLMConfig, should_invoke_l2, parse_llm_config_from_headers


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = LLMConfig()
        assert config.enabled is False
        assert config.base_url == "https://coding.dashscope.aliyuncs.com/apps/anthropic"
        assert config.model == "qwen3.6-plus"
        assert config.threshold == 0.8
        assert config.api_key == ""
        assert config.timeout == 60  # Increased for DashScope API latency

    def test_custom_values(self):
        """Test custom configuration."""
        config = LLMConfig(
            enabled=True,
            base_url="https://api.anthropic.com",
            model="claude-3-opus",
            threshold=0.5,
            api_key="sk-test-123",
            timeout=60,
        )
        assert config.enabled is True
        assert config.model == "claude-3-opus"
        assert config.threshold == 0.5


class TestShouldInvokeL2:
    """Tests for should_invoke_l2 routing logic."""

    def _make_l1_result(
        self,
        owner: OwnerTeam = OwnerTeam.AGENT_TEAM,
        confidence: float = 0.9,
    ) -> TriageResult:
        """Helper to create L1 result."""
        return TriageResult(
            primary_owner=owner,
            confidence=confidence,
            root_cause="Test root cause",
            source=TriageSource.RULES,
        )

    def test_disabled_config_returns_false(self):
        """L2 should not trigger when disabled."""
        config = LLMConfig(enabled=False, api_key="sk-test")
        l1 = self._make_l1_result(confidence=0.3)  # Low confidence
        assert should_invoke_l2(l1, config) is False

    def test_no_api_key_returns_false(self):
        """L2 should not trigger without API key."""
        config = LLMConfig(enabled=True, api_key="")
        l1 = self._make_l1_result(confidence=0.3)
        assert should_invoke_l2(l1, config) is False

    def test_unknown_owner_triggers_l2(self):
        """L2 should trigger when L1 returns UNKNOWN owner."""
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)
        l1 = self._make_l1_result(owner=OwnerTeam.UNKNOWN, confidence=0.9)
        assert should_invoke_l2(l1, config) is True

    def test_low_confidence_triggers_l2(self):
        """L2 should trigger when confidence below threshold."""
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)
        l1 = self._make_l1_result(confidence=0.5)
        assert should_invoke_l2(l1, config) is True

    def test_high_confidence_does_not_trigger_l2(self):
        """L2 should not trigger when confidence at or above threshold."""
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)
        l1 = self._make_l1_result(confidence=0.85)
        assert should_invoke_l2(l1, config) is False

    def test_exact_threshold_does_not_trigger(self):
        """L2 should not trigger when confidence equals threshold."""
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)
        l1 = self._make_l1_result(confidence=0.8)
        assert should_invoke_l2(l1, config) is False

    def test_threshold_boundary(self):
        """Test threshold boundary conditions."""
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.8)

        # Just below threshold
        l1_low = self._make_l1_result(confidence=0.79)
        assert should_invoke_l2(l1_low, config) is True

        # Just at threshold
        l1_at = self._make_l1_result(confidence=0.80)
        assert should_invoke_l2(l1_at, config) is False

    def test_custom_threshold(self):
        """Test with custom threshold value."""
        config = LLMConfig(enabled=True, api_key="sk-test", threshold=0.5)

        l1_high = self._make_l1_result(confidence=0.6)
        assert should_invoke_l2(l1_high, config) is False

        l1_low = self._make_l1_result(confidence=0.4)
        assert should_invoke_l2(l1_low, config) is True


class TestParseLLMConfigFromHeaders:
    """Tests for parse_llm_config_from_headers."""

    def test_disabled_returns_none(self):
        """Returns None when LLM not enabled."""
        headers = {"x-llm-enabled": "false", "x-llm-api-key": "sk-test"}
        assert parse_llm_config_from_headers(headers) is None

    def test_missing_enabled_returns_none(self):
        """Returns None when enabled header missing."""
        headers = {"x-llm-api-key": "sk-test"}
        assert parse_llm_config_from_headers(headers) is None

    def test_no_api_key_returns_none(self):
        """Returns None when API key missing."""
        headers = {"x-llm-enabled": "true"}
        assert parse_llm_config_from_headers(headers) is None

    def test_empty_api_key_returns_none(self):
        """Returns None when API key is empty."""
        headers = {"x-llm-enabled": "true", "x-llm-api-key": ""}
        assert parse_llm_config_from_headers(headers) is None

    def test_minimal_valid_config(self):
        """Test minimal valid configuration."""
        headers = {
            "x-llm-enabled": "true",
            "x-llm-api-key": "sk-test-123",
        }
        config = parse_llm_config_from_headers(headers)

        assert config is not None
        assert config.enabled is True
        assert config.api_key == "sk-test-123"
        # Should use defaults for other fields
        assert config.base_url == "https://coding.dashscope.aliyuncs.com/apps/anthropic"
        assert config.model == "qwen3.6-plus"
        assert config.threshold == 0.8
        assert config.timeout == 60  # Default increased for DashScope API latency

    def test_full_config(self):
        """Test full configuration from headers."""
        headers = {
            "x-llm-enabled": "true",
            "x-llm-api-key": "sk-anthropic-key",
            "x-llm-base-url": "https://api.anthropic.com",
            "x-llm-model": "claude-3-opus",
            "x-llm-threshold": "0.6",
            "x-llm-timeout": "45",
        }
        config = parse_llm_config_from_headers(headers)

        assert config is not None
        assert config.enabled is True
        assert config.api_key == "sk-anthropic-key"
        assert config.base_url == "https://api.anthropic.com"
        assert config.model == "claude-3-opus"
        assert config.threshold == 0.6
        assert config.timeout == 45

    def test_case_insensitive_enabled(self):
        """Test enabled header is case insensitive."""
        headers_upper = {"x-llm-enabled": "TRUE", "x-llm-api-key": "sk-test"}
        config = parse_llm_config_from_headers(headers_upper)
        assert config is not None
        assert config.enabled is True

        headers_mixed = {"x-llm-enabled": "True", "x-llm-api-key": "sk-test"}
        config = parse_llm_config_from_headers(headers_mixed)
        assert config is not None

    def test_header_keys_are_lowercase(self):
        """Verify headers are expected in lowercase."""
        # This tests the expected input format
        headers = {
            "x-llm-enabled": "true",
            "x-llm-api-key": "sk-test",
        }
        config = parse_llm_config_from_headers(headers)
        assert config is not None
