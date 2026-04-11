"""Three-layer fault attribution engine."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from models import (
    OTelSpan,
    OwnerTeam,
    SpanLayer,
    SpanTree,
    TriageResult,
    get_effective_layer,
    layer_to_owner,
)


# ---------------------------------------------------------------------------
# Rule models
# ---------------------------------------------------------------------------

@dataclass
class CrossSpanCondition:
    """A condition that checks a related span (parent/sibling/ancestor/child)."""
    relation: str  # parent | sibling | ancestor | child
    span_pattern: Optional[str] = None
    attribute: Optional[dict[str, Any]] = None
    status: Optional[str] = None


@dataclass
class PatternMatchCondition:
    """Special pattern detection (loops, swallowed errors)."""
    type: str  # repetition | swallowed_error
    span_pattern: Optional[str] = None
    parent_pattern: Optional[str] = None
    min_count: int = 5
    check_attribute: Optional[str] = None
    parent_status: Optional[str] = None
    child_has_error: bool = False


@dataclass
class TriageRule:
    """A single triage rule loaded from YAML."""
    span_pattern: str = "*"
    status: Optional[str] = None
    error_type: Optional[list[str]] = None
    error_contains: Optional[str] = None
    attribute: Optional[dict[str, Any]] = None
    root_span_error: Optional[bool] = None
    no_child_error: Optional[bool] = None
    cross_span: list[CrossSpanCondition] = field(default_factory=list)
    pattern_match: Optional[PatternMatchCondition] = None
    owner: str = "unknown"
    co_responsible: list[str] = field(default_factory=list)
    confidence: float = 0.8
    reason: str = ""
    name: str = ""


# ---------------------------------------------------------------------------
# Rule loader
# ---------------------------------------------------------------------------

def load_rules(path: str | Path) -> list[TriageRule]:
    """Load triage rules from a YAML file."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    rules: list[TriageRule] = []
    for raw in data.get("rules", []):
        match = raw.get("match", {})

        # Parse cross_span conditions — support both formats:
        #   Format A (opus-45): { relation: "sibling", span_pattern: "..." }
        #   Format B (opus):    { sibling_pattern: "..." }
        cross_raw = raw.get("cross_span", [])
        cross_conditions = []
        for cs in cross_raw:
            relation = cs.get("relation", "parent")
            pattern = cs.get("span_pattern")
            # Also support Format B: key-based relation
            if not pattern:
                for rel in ("parent_pattern", "sibling_pattern", "ancestor_pattern", "child_pattern"):
                    if rel in cs:
                        relation = rel.replace("_pattern", "")
                        pattern = cs[rel]
                        break
            cross_conditions.append(CrossSpanCondition(
                relation=relation,
                span_pattern=pattern,
                attribute=cs.get("attribute"),
                status=cs.get("status"),
            ))

        # Parse pattern_match (special detection)
        pm_raw = raw.get("pattern_match")
        pattern_match = None
        if pm_raw:
            pattern_match = PatternMatchCondition(
                type=pm_raw.get("type", ""),
                span_pattern=pm_raw.get("span_pattern"),
                parent_pattern=pm_raw.get("parent_pattern"),
                min_count=pm_raw.get("min_count", 5),
                check_attribute=pm_raw.get("check_attribute"),
                parent_status=pm_raw.get("parent_status"),
                child_has_error=pm_raw.get("child_has_error", False),
            )

        rules.append(TriageRule(
            span_pattern=match.get("span_pattern", "*"),
            status=match.get("status"),
            error_type=match.get("error_type"),
            error_contains=match.get("error_contains"),
            attribute=match.get("attribute"),
            root_span_error=match.get("root_span_error"),
            no_child_error=match.get("no_child_error"),
            cross_span=cross_conditions,
            pattern_match=pattern_match,
            owner=raw.get("owner", "unknown"),
            co_responsible=raw.get("co_responsible", []),
            confidence=raw.get("confidence", 0.8),
            reason=raw.get("reason", ""),
            name=raw.get("name", ""),
        ))
    return rules


# ---------------------------------------------------------------------------
# Span matching helpers
# ---------------------------------------------------------------------------

def _match_pattern(name: str, pattern: str) -> bool:
    """Match span name against pattern. Supports regex (^...) and glob (llm.*)."""
    if pattern == "*":
        return True
    # Regex pattern (starts with ^, or contains regex metacharacters)
    if pattern.startswith("^") or pattern.startswith("("):
        try:
            return bool(re.match(pattern, name, re.IGNORECASE))
        except re.error:
            return False
    # Glob-style: "llm.*" matches "llm.chat"
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return name.lower().startswith(prefix.lower() + ".")
    # Pipe-separated patterns: "llm.*|gen_ai.*"
    if "|" in pattern:
        return any(_match_pattern(name, p.strip()) for p in pattern.split("|"))
    return name.lower() == pattern.lower()


def _match_attributes(span: OTelSpan, required: dict[str, Any]) -> bool:
    """Check if span attributes contain all required key-value pairs."""
    for key, value in required.items():
        actual = span.get_attr(key)
        if actual is None:
            return False
        # Support list matching (any value in list)
        if isinstance(value, list):
            if actual not in value:
                return False
        elif str(actual) != str(value):
            return False
    return True


def _match_single_span(span: OTelSpan, rule: TriageRule, tree: Optional[SpanTree] = None) -> bool:
    """Check if a span matches a rule's single-span conditions."""
    # pattern_match rules are handled separately
    if rule.pattern_match:
        return False

    if rule.span_pattern != "*" and not _match_pattern(span.name, rule.span_pattern):
        return False

    if rule.status and span.status.value != rule.status:
        return False

    if rule.error_type:
        error_type = span.get_attr("error.type", span.status_message or "")
        if not any(et.lower() in str(error_type).lower() for et in rule.error_type):
            return False

    if rule.error_contains:
        error_msg = span.status_message or span.get_attr("error.message", "")
        # Support regex in error_contains (e.g., "parse|JSON|format")
        try:
            if not re.search(rule.error_contains, str(error_msg), re.IGNORECASE):
                return False
        except re.error:
            if rule.error_contains.lower() not in str(error_msg).lower():
                return False

    if rule.attribute:
        if not _match_attributes(span, rule.attribute):
            return False

    # root_span_error: only match if this is a root span with ERROR
    if rule.root_span_error is True:
        if tree is None:
            return False
        if span.span_id not in tree.root_spans or span.status.value != "ERROR":
            return False

    # no_child_error: only match if no child spans have ERROR
    if rule.no_child_error is True:
        if tree is None:
            return False
        child_ids = tree.children.get(span.span_id, [])
        has_child_error = any(
            tree.spans[cid].status.value == "ERROR"
            for cid in child_ids if cid in tree.spans
        )
        if has_child_error:
            return False

    return True


# ---------------------------------------------------------------------------
# Cross-span matching
# ---------------------------------------------------------------------------

def _get_related_spans(
    span: OTelSpan, tree: SpanTree, relation: str, max_depth: int = 5
) -> list[OTelSpan]:
    """Get spans related to the given span by the specified relation."""
    results: list[OTelSpan] = []

    if relation == "parent":
        if span.parent_span_id and span.parent_span_id in tree.spans:
            results.append(tree.spans[span.parent_span_id])

    elif relation == "sibling":
        if span.parent_span_id and span.parent_span_id in tree.children:
            for child_id in tree.children[span.parent_span_id]:
                if child_id != span.span_id and child_id in tree.spans:
                    results.append(tree.spans[child_id])

    elif relation == "ancestor":
        current = span
        for _ in range(max_depth):
            if current.parent_span_id and current.parent_span_id in tree.spans:
                parent = tree.spans[current.parent_span_id]
                results.append(parent)
                current = parent
            else:
                break

    elif relation == "child":
        for child_id in tree.children.get(span.span_id, []):
            if child_id in tree.spans:
                results.append(tree.spans[child_id])

    return results


def _match_cross_span(
    span: OTelSpan, tree: SpanTree, conditions: list[CrossSpanCondition]
) -> bool:
    """Check if all cross-span conditions are satisfied."""
    for cond in conditions:
        related = _get_related_spans(span, tree, cond.relation)
        matched = False
        for rel_span in related:
            if cond.span_pattern and not _match_pattern(rel_span.name, cond.span_pattern):
                continue
            if cond.status and rel_span.status.value != cond.status:
                continue
            if cond.attribute and not _match_attributes(rel_span, cond.attribute):
                continue
            matched = True
            break
        if not matched:
            return False
    return True


# ---------------------------------------------------------------------------
# Three-layer attribution
# ---------------------------------------------------------------------------

def _find_error_spans(tree: SpanTree) -> list[OTelSpan]:
    """Find all ERROR spans, sorted by depth (deepest first)."""
    error_spans = [
        s for s in tree.spans.values()
        if s.status == "ERROR"
    ]
    error_spans.sort(key=lambda s: s.depth, reverse=True)
    return error_spans


def _find_anomaly_spans(tree: SpanTree) -> list[OTelSpan]:
    """Find non-ERROR spans that indicate problems (content_filter, max_tokens, etc.)."""
    anomalies: list[OTelSpan] = []
    for span in tree.spans.values():
        if span.status.value == "ERROR":
            continue
        # Check for content filter / max_tokens
        # Support both naming conventions:
        # 1. gen_ai.response.finish_reasons (OTel semantic convention)
        # 2. finish_reasons (OpenCode trace)
        finish_reasons = (
            span.get_attr("gen_ai.response.finish_reasons") or
            span.get_attr("finish_reasons")
        )
        if finish_reasons in ("content_filter", ["content_filter"]):
            anomalies.append(span)
        elif finish_reasons in ("max_tokens", ["max_tokens"]):
            anomalies.append(span)
    return anomalies


def _detect_loop_pattern(tree: SpanTree) -> Optional[OTelSpan]:
    """Detect tool_use loop pattern: same tool called 5+ times with OK status."""
    tool_calls: dict[str, list[OTelSpan]] = {}
    for span in tree.spans.values():
        # Match both naming conventions:
        # 1. Prefix-based: mcp.*, gen_ai.*
        # 2. OpenCode trace: tool_call, model_inference
        is_tool_span = (
            _match_pattern(span.name, "mcp.*") or
            _match_pattern(span.name, "gen_ai.*") or
            span.name.lower() in ("tool_call", "model_inference")
        )
        if is_tool_span:
            # Get tool identifier from attributes
            tool_name = (
                span.get_attr("function_name") or  # OpenCode tool_call
                span.get_attr("mcp.tool") or
                span.get_attr("gen_ai.request.model") or
                span.get_attr("model") or  # OpenCode model_inference
                span.name
            )
            tool_calls.setdefault(str(tool_name), []).append(span)

    for tool_name, spans in tool_calls.items():
        if len(spans) >= 5:
            # All OK but repeated → loop pattern
            if all(s.status.value != "ERROR" for s in spans):
                return spans[0]  # Return first as representative
    return None


def layer1_direct_attribution(tree: SpanTree) -> Optional[OTelSpan]:
    """Layer 1: Find the deepest ERROR span as initial root cause candidate."""
    error_spans = _find_error_spans(tree)
    if error_spans:
        return error_spans[0]  # Deepest first

    # Check for anomaly spans (non-ERROR but problematic)
    anomalies = _find_anomaly_spans(tree)
    if anomalies:
        return anomalies[0]

    # Check for loop patterns
    loop_span = _detect_loop_pattern(tree)
    if loop_span:
        return loop_span

    return None


def layer2_upstream_propagation(
    candidate: OTelSpan, tree: SpanTree
) -> tuple[OTelSpan, list[str]]:
    """
    Layer 2: Check if the root cause should be attributed upstream.

    Returns (actual_root_cause, reasons_for_shift).
    """
    reasons: list[str] = []
    current = candidate

    # Walk up the parent chain looking for upstream causes
    visited = {current.span_id}
    while current.parent_span_id and current.parent_span_id in tree.spans:
        parent = tree.spans[current.parent_span_id]
        if parent.span_id in visited:
            break
        visited.add(parent.span_id)

        shifted = False

        # Check: parent passed invalid input
        input_valid = parent.get_attr("mcp.tool.input_valid")
        if input_valid is False:
            reasons.append(f"Parent span '{parent.name}' passed invalid input (mcp.tool.input_valid=false)")
            current = parent
            shifted = True

        # Check: sibling has truncation that could cause downstream parse failure
        if not shifted and parent.parent_span_id:
            siblings = _get_related_spans(current, tree, "sibling")
            for sib in siblings:
                # Support both attribute naming conventions
                finish = sib.get_attr("gen_ai.response.finish_reasons") or sib.get_attr("finish_reasons")
                if finish in ("max_tokens", ["max_tokens"]):
                    reasons.append(
                        f"Sibling span '{sib.name}' had finish_reason=max_tokens (output truncated)"
                    )
                    current = sib
                    shifted = True
                    break

        # Check: ancestor gen_ai span has truncation
        if not shifted:
            ancestors = _get_related_spans(current, tree, "ancestor")
            for anc in ancestors:
                # Support both attribute naming conventions
                finish = anc.get_attr("gen_ai.response.finish_reasons") or anc.get_attr("finish_reasons")
                if finish in ("max_tokens", ["max_tokens"]):
                    reasons.append(
                        f"Ancestor span '{anc.name}' had finish_reason=max_tokens (output truncated)"
                    )
                    current = anc
                    shifted = True
                    break

        # Check: Agent timeout too short (cancel vs real timeout)
        if not shifted and get_effective_layer(current) == SpanLayer.MCP:
            agent_timeout = parent.get_attr("agent.timeout_ms")
            if agent_timeout and current.duration_ms > 0:
                error_type = current.get_attr("error.type", current.status_message or "")
                if "cancel" in str(error_type).lower() or "timeout" in str(error_type).lower():
                    if current.duration_ms < agent_timeout * 2:
                        # MCP was still within reasonable time but Agent cancelled
                        reasons.append(
                            f"Agent timeout ({agent_timeout}ms) may be too short for '{current.name}' "
                            f"(ran {current.duration_ms:.0f}ms before cancel)"
                        )
                        current = parent
                        shifted = True

        if not shifted:
            break

    return current, reasons


def layer3_tolerance_analysis(
    root_cause: OTelSpan, tree: SpanTree
) -> list[OwnerTeam]:
    """
    Layer 3: Check if Agent should share responsibility for lacking error handling.

    Returns list of co-responsible teams.
    """
    co_responsible: list[OwnerTeam] = []

    # If root cause is not in Agent layer, check if Agent had retry/fallback
    if get_effective_layer(root_cause) != SpanLayer.AGENT:
        # Walk up to find the enclosing Agent span
        agent_span = None
        current = root_cause
        while current.parent_span_id and current.parent_span_id in tree.spans:
            parent = tree.spans[current.parent_span_id]
            if get_effective_layer(parent) == SpanLayer.AGENT:
                agent_span = parent
                break
            current = parent

        if agent_span:
            # Check if Agent has retry spans
            agent_children = tree.children.get(agent_span.span_id, [])
            has_retry = any(
                "retry" in tree.spans[cid].name.lower()
                for cid in agent_children
                if cid in tree.spans
            )
            has_fallback = agent_span.get_attr("agent.has_fallback", False)

            if not has_retry and not has_fallback:
                co_responsible.append(OwnerTeam.AGENT_TEAM)

    # Check for hidden failures: root span OK but child spans have errors
    for root_id in tree.root_spans:
        root_span = tree.spans.get(root_id)
        if root_span and root_span.status.value == "OK":
            child_errors = [
                tree.spans[cid] for cid in tree.children.get(root_id, [])
                if cid in tree.spans and tree.spans[cid].status.value == "ERROR"
            ]
            if child_errors:
                # Agent swallowed errors
                if OwnerTeam.AGENT_TEAM not in co_responsible:
                    co_responsible.append(OwnerTeam.AGENT_TEAM)

    return co_responsible


# ---------------------------------------------------------------------------
# Evidence chain
# ---------------------------------------------------------------------------

def _build_fault_chain(span: OTelSpan, tree: SpanTree) -> list[OTelSpan]:
    """Build evidence chain from root cause span up to root."""
    chain = [span]
    current = span
    visited = {span.span_id}
    while current.parent_span_id and current.parent_span_id in tree.spans:
        if current.parent_span_id in visited:
            break
        visited.add(current.parent_span_id)
        parent = tree.spans[current.parent_span_id]
        chain.append(parent)
        current = parent
    return chain


# ---------------------------------------------------------------------------
# Confidence calculation
# ---------------------------------------------------------------------------

def _calculate_confidence(
    rule_confidence: float,
    upstream_reasons: list[str],
    co_responsible: list[OwnerTeam],
    error_spans_count: int,
    anomaly: bool = False,
) -> float:
    """Calculate quantified confidence score (0.0-1.0)."""
    score = rule_confidence

    # Upstream shift detected → slightly lower confidence
    if upstream_reasons:
        score *= 0.9

    # Multiple responsible parties → lower confidence
    if co_responsible:
        score *= 0.85

    # Many error spans (complex failure) → lower confidence
    if error_spans_count > 3:
        score *= 0.8

    # Anomaly-based (no ERROR) → lower confidence
    if anomaly:
        score *= 0.75

    return round(min(max(score, 0.0), 1.0), 2)


# ---------------------------------------------------------------------------
# Pattern-based rule matching
# ---------------------------------------------------------------------------

def _match_pattern_rule(pm: PatternMatchCondition, tree: SpanTree) -> bool:
    """Check if a pattern_match rule matches the trace."""
    if pm.type == "repetition":
        # Check for repeated span pattern
        matching_spans: dict[str, list[OTelSpan]] = {}
        for span in tree.spans.values():
            if pm.span_pattern and _match_pattern(span.name, pm.span_pattern):
                key = span.get_attr(pm.check_attribute, span.name) if pm.check_attribute else span.name
                matching_spans.setdefault(str(key), []).append(span)
        for _key, spans in matching_spans.items():
            if len(spans) >= pm.min_count:
                if all(s.status.value != "ERROR" for s in spans):
                    return True

    elif pm.type == "swallowed_error":
        # Check for parent OK + child ERROR
        for span in tree.spans.values():
            if pm.parent_pattern and not _match_pattern(span.name, pm.parent_pattern):
                continue
            if pm.parent_status and span.status.value != pm.parent_status:
                continue
            if pm.child_has_error:
                child_ids = tree.children.get(span.span_id, [])
                has_child_err = any(
                    tree.spans[cid].status.value == "ERROR"
                    for cid in child_ids if cid in tree.spans
                )
                if has_child_err:
                    return True

    return False


# ---------------------------------------------------------------------------
# Main triage function
# ---------------------------------------------------------------------------

def triage(tree: SpanTree, rules: list[TriageRule]) -> TriageResult:
    """
    Run three-layer fault attribution on a span tree.

    1. Layer 1: Direct attribution (deepest ERROR span)
    2. Layer 2: Upstream propagation analysis
    3. Layer 3: Tolerance/fallback analysis
    """
    # Layer 1: Find root cause candidate
    candidate = layer1_direct_attribution(tree)

    if candidate is None:
        return TriageResult(
            primary_owner=OwnerTeam.UNKNOWN,
            confidence=0.0,
            root_cause="No error or anomaly detected in trace",
        )

    is_anomaly = candidate.status.value != "ERROR"
    error_spans = _find_error_spans(tree)

    # Layer 2: Upstream propagation
    root_cause_span, upstream_reasons = layer2_upstream_propagation(candidate, tree)

    # Check pattern_match rules first (loops, swallowed errors)
    for rule in rules:
        if rule.pattern_match and _match_pattern_rule(rule.pattern_match, tree):
            # Pattern-based detection overrides normal flow
            primary = OwnerTeam(rule.owner)
            rule_co = [OwnerTeam(co) for co in rule.co_responsible]
            tolerance_co = layer3_tolerance_analysis(root_cause_span, tree)
            all_co = list(set(rule_co + tolerance_co))
            all_co = [co for co in all_co if co != primary]
            fault_chain = _build_fault_chain(root_cause_span, tree)
            confidence = _calculate_confidence(rule.confidence, [], all_co, len(error_spans), True)
            return TriageResult(
                primary_owner=primary,
                co_responsible=all_co,
                confidence=confidence,
                fault_span=root_cause_span,
                fault_chain=fault_chain,
                root_cause=rule.reason or f"Pattern detected: {rule.pattern_match.type}",
                action_items=_build_action_items(primary, all_co, root_cause_span, []),
            )

    # Match standard rules
    matched_rule: Optional[TriageRule] = None
    for rule in rules:
        if rule.pattern_match:
            continue
        if _match_single_span(root_cause_span, rule, tree):
            if not rule.cross_span or _match_cross_span(root_cause_span, tree, rule.cross_span):
                matched_rule = rule
                break

    # Determine primary owner
    if matched_rule:
        primary = OwnerTeam(matched_rule.owner)
        rule_co = [OwnerTeam(co) for co in matched_rule.co_responsible]
        rule_confidence = matched_rule.confidence
        reason_text = matched_rule.reason or f"Matched rule: {matched_rule.span_pattern}"
    else:
        effective_layer = get_effective_layer(root_cause_span)
        primary = layer_to_owner(effective_layer)
        rule_co = []
        rule_confidence = 0.6  # No matching rule → lower confidence
        reason_text = f"No matching rule; attributed by span layer: {effective_layer.value}"

    # Layer 3: Tolerance analysis
    tolerance_co = layer3_tolerance_analysis(root_cause_span, tree)

    # Merge co-responsible
    all_co = list(set(rule_co + tolerance_co))
    # Remove primary from co-responsible
    all_co = [co for co in all_co if co != primary]

    # Build evidence chain
    fault_chain = _build_fault_chain(root_cause_span, tree)

    # Calculate confidence
    confidence = _calculate_confidence(
        rule_confidence, upstream_reasons, all_co, len(error_spans), is_anomaly
    )

    # Build root cause description
    root_cause_desc = reason_text
    if upstream_reasons:
        root_cause_desc += " | Upstream: " + "; ".join(upstream_reasons)

    # Build action items
    action_items = _build_action_items(primary, all_co, root_cause_span, upstream_reasons)

    return TriageResult(
        primary_owner=primary,
        co_responsible=all_co,
        confidence=confidence,
        fault_span=root_cause_span,
        fault_chain=fault_chain,
        root_cause=root_cause_desc,
        action_items=action_items,
    )


def _build_action_items(
    primary: OwnerTeam,
    co_responsible: list[OwnerTeam],
    fault_span: OTelSpan,
    upstream_reasons: list[str],
) -> list[str]:
    """Generate actionable items for each responsible team."""
    items: list[str] = []

    items.append(f"[{primary.value}] Investigate root cause in span '{fault_span.name}': {fault_span.status_message or 'see attributes'}")

    for co in co_responsible:
        if co == OwnerTeam.AGENT_TEAM:
            items.append(f"[{co.value}] Add error handling/retry/fallback for downstream failures")
        else:
            items.append(f"[{co.value}] Review related span behavior")

    if upstream_reasons:
        items.append(f"[upstream] Root cause shifted due to: {'; '.join(upstream_reasons)}")

    return items
