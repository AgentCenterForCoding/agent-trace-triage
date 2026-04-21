"""Static risk-word scanning for SOP bodies."""

RISKY_TERMS: tuple[str, ...] = (
    "自动执行",
    "自动 push",
    "自动push",
    "无需确认",
    "静默",
    "立即执行",
    "--force",
    "-f ",
    "rm -rf",
    "git push -f",
    "git push --force",
    "sudo ",
)


def scan_risky_terms(text: str) -> list[str]:
    """Return the list of risk terms that appear in `text` (case-insensitive for ASCII)."""
    if not text:
        return []
    hay = text.lower()
    hits: list[str] = []
    for term in RISKY_TERMS:
        if term.lower() in hay:
            hits.append(term)
    return hits
