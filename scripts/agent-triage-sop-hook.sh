#!/usr/bin/env bash
# OpenCode session.start Hook wrapper for Unix.
# Configure in ~/.opencode/config.json with an absolute path to this file.
set -e
PROJECT_ROOT="${AGENT_TRIAGE_PROJECT_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PROJECT_ROOT/backend"
exec python -m sop.hook_cli
