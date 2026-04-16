#!/usr/bin/env bash
# Batch triage diagnostic script
# Usage:
#   ./script/triage_batch.sh                         # Run all 40 traces
#   ./script/triage_batch.sh sample_traces/4_1*.json # Run specific traces
#   ./script/triage_batch.sh --dry-run               # Show trace catalog only

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$PROJECT_DIR/script/triage_results"
SKILL_PATH="$PROJECT_DIR/skills/agent-trace-triage"

mkdir -p "$RESULTS_DIR"

DRY_RUN=false
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=true
  shift
fi

if [[ $# -gt 0 ]]; then
  FILES=("$@")
else
  FILES=("$PROJECT_DIR"/sample_traces/*.json)
fi

TOTAL=${#FILES[@]}
PASS=0
FAIL=0
ERRORS=()

echo "=== Agent Trace Triage Batch Test ==="
echo "Traces: $TOTAL"
echo "Results: $RESULTS_DIR"
echo ""

for i in "${!FILES[@]}"; do
  FILE="${FILES[$i]}"
  BASENAME=$(basename "$FILE" .json)
  IDX=$((i + 1))

  if $DRY_RUN; then
    echo "[$IDX/$TOTAL] $BASENAME"
    continue
  fi

  echo -n "[$IDX/$TOTAL] $BASENAME ... "

  RESULT_FILE="$RESULTS_DIR/$BASENAME.jsonl"
  PARSED_FILE="$RESULTS_DIR/$BASENAME.result.json"

  TRACE_CONTENT=$(cat "$FILE")

  if opencode run "请使用 agent-trace-triage skill 分析以下 trace，直接输出归因结果的 JSON（包含 primary_owner, co_responsible, confidence, root_cause, action_items 字段）。Trace 内容：$TRACE_CONTENT" \
    --format json \
    > "$RESULT_FILE" 2>/dev/null; then

    # Extract triage JSON from text events
    TRIAGE_JSON=$(python -c "
import json, re, sys
texts = []
for line in open('$RESULT_FILE', encoding='utf-8'):
    line = line.strip()
    if not line:
        continue
    try:
        event = json.loads(line)
        if event.get('type') == 'text':
            part = event.get('part', {})
            texts.append(part.get('text', ''))
    except json.JSONDecodeError:
        pass
full_text = ''.join(texts)
# Match ```json ... ``` block (handle nested braces)
match = re.search(r'\x60\x60\x60json\s*(.*?)\s*\x60\x60\x60', full_text, re.DOTALL)
if match:
    try:
        result = json.loads(match.group(1))
        if isinstance(result, dict) and 'primary_owner' in result:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            sys.exit(0)
    except json.JSONDecodeError:
        pass
sys.exit(1)
" 2>/dev/null)

    if [[ -n "$TRIAGE_JSON" ]]; then
      echo "$TRIAGE_JSON" > "$PARSED_FILE"
      OWNER=$(echo "$TRIAGE_JSON" | python -c "import json,sys; print(json.load(sys.stdin).get('primary_owner','?'))")
      CONF=$(echo "$TRIAGE_JSON" | python -c "import json,sys; print(json.load(sys.stdin).get('confidence','?'))")
      echo "OK  owner=$OWNER  confidence=$CONF"
      PASS=$((PASS + 1))
    else
      echo "PARSE_FAIL (no JSON in output)"
      ERRORS+=("$BASENAME: output parsing failed")
      FAIL=$((FAIL + 1))
    fi
  else
    echo "CLI_FAIL"
    ERRORS+=("$BASENAME: opencode run failed")
    FAIL=$((FAIL + 1))
  fi
done

if ! $DRY_RUN; then
  echo ""
  echo "=== Summary ==="
  echo "Total: $TOTAL  Pass: $PASS  Fail: $FAIL"

  if [[ ${#ERRORS[@]} -gt 0 ]]; then
    echo ""
    echo "Failures:"
    for err in "${ERRORS[@]}"; do
      echo "  - $err"
    done
  fi

  # Write summary
  cat > "$RESULTS_DIR/summary.json" <<EOFSUM
{
  "total": $TOTAL,
  "pass": $PASS,
  "fail": $FAIL,
  "errors": $(python -c "import json; print(json.dumps([$(printf '"%s",' "${ERRORS[@]:-}" | sed 's/,$//')])"))" 2>/dev/null || echo "[]")
}
EOFSUM
fi
