"""OpenCode `session.start` Hook: fetch top-K SOP via backend API and print to stdout.

Behaviour contract (spec: sop-hook-injector):
- Resolve user_id from AGENT_TRIAGE_USER or OS login. On failure: exit 2, stdout empty.
- GET {AGENT_TRIAGE_API_URL or http://localhost:3014}/api/v1/sops/retrieve?user_id=&k=3
- 500ms timeout; on any network/HTTP error: exit 0, stdout empty, stderr warning.
- Prepend header / append footer; skip both when list is empty.
- Cap output at 8KB; drop lower-ranked SOP bodies; log to stderr.
- Warn in stderr when total elapsed > 500ms.
- Read-only; no file writes; no shell commands.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
import time
from typing import Optional

HEADER = "--- AgentTriage SOP Suggestions (非强制执行，仅供参考) ---"
FOOTER = "--- End of SOP Suggestions ---"
BYTE_CAP = 8 * 1024
K = 3
API_TIMEOUT_SECS = 0.5


def _resolve_user() -> Optional[str]:
    u = os.environ.get("AGENT_TRIAGE_USER")
    if u:
        return u
    try:
        return getpass.getuser()
    except Exception:
        return None


def _api_base() -> str:
    return os.environ.get("AGENT_TRIAGE_API_URL", "http://localhost:3014").rstrip("/")


def _fetch_sops(user_id: str) -> list[dict]:
    # Use stdlib urllib so cold-start stays under the 200ms P99 budget;
    # bypass proxy env vars since the hook always talks to localhost.
    import json as _json
    import urllib.parse
    import urllib.request

    params = urllib.parse.urlencode({"user_id": user_id, "k": K})
    url = f"{_api_base()}/api/v1/sops/retrieve?{params}"
    req = urllib.request.Request(url, method="GET")
    key = os.environ.get("AGENT_TRIAGE_API_KEY")
    if key:
        req.add_header("X-API-Key", key)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=API_TIMEOUT_SECS) as resp:
        if resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status}")
        data = _json.loads(resp.read().decode("utf-8"))
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict) and "body" in x]


def _format_output(items: list[dict]) -> str:
    if not items:
        return ""
    out: list[str] = [HEADER]
    dropped = 0
    for item in items:
        body = str(item.get("body", "")).strip()
        if not body:
            continue
        candidate_chunk = "\n" + body + "\n"
        tentative = "\n".join(out) + candidate_chunk + "\n" + FOOTER
        if len(tentative.encode("utf-8")) > BYTE_CAP:
            dropped += 1
            continue
        out.append(body)
    out.append(FOOTER)
    if dropped:
        print(f"dropped {dropped} by byte cap", file=sys.stderr)
    if len(out) == 2:
        return ""
    return "\n".join(out) + "\n"


def main() -> int:
    start = time.perf_counter()
    user = _resolve_user()
    if not user:
        print("error: cannot resolve user_id", file=sys.stderr)
        return 2

    try:
        items = _fetch_sops(user)
    except Exception as exc:
        print(f"SOP API unavailable: {exc}; skipping injection", file=sys.stderr)
        return 0

    output = _format_output(items)
    if output:
        sys.stdout.write(output)
        sys.stdout.flush()

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    if elapsed_ms > 500:
        print(f"hook latency warn: {elapsed_ms:.0f}ms", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
