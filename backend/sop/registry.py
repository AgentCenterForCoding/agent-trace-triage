"""SOP registry: markdown file storage under backend/data/sops/<user>/."""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

from .models import SOP, SOP_BASE, SOPMeta, SOPStep, utcnow

_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


MUTUALLY_EXCLUSIVE_ACTION_PAIRS: tuple[tuple[str, str], ...] = (
    ("git_push", "create_mr"),
    ("force_push", "create_mr"),
    ("git_push_force", "create_mr"),
)


def _user_dir(user_id: str) -> Path:
    if not user_id or not _USER_ID_PATTERN.match(user_id):
        raise PermissionError(f"invalid user_id: {user_id!r}")
    base = SOP_BASE.resolve()
    target = (SOP_BASE / user_id).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise PermissionError(f"user_id escapes base dir: {user_id!r}") from exc
    return target


def _ensure_dir(user_id: str) -> Path:
    d = _user_dir(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _atomic_write(path: Path, content: str) -> None:
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".md")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        os.replace(tmp_name, path)
    except Exception:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
        raise


def _serialize(sop: SOP) -> str:
    fm = yaml.safe_dump(sop.meta.model_dump(), sort_keys=False, allow_unicode=True).strip()
    lines = [f"- {s.action}" + (f" {s.args}" if s.args else "") for s in sop.steps]
    return f"---\n{fm}\n---\n\n## 意图\n\n{sop.intent}\n\n## 步骤\n\n" + "\n".join(lines) + "\n"


def _deserialize(path: Path) -> SOP:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"missing frontmatter: {path}")
    _, fm_raw, body = text.split("---", 2)
    meta_dict = yaml.safe_load(fm_raw) or {}
    meta = SOPMeta(**meta_dict)
    intent = ""
    steps: list[SOPStep] = []
    current_section: Optional[str] = None
    for raw in body.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current_section = line[3:].strip()
            continue
        if not line:
            continue
        if current_section == "意图" and not intent:
            intent = line
        elif current_section == "步骤" and line.startswith("- "):
            m = re.match(r"^- (\S+)(?:\s+(\{.*\}))?$", line)
            action = m.group(1) if m else line[2:].strip()
            steps.append(SOPStep(action=action))
    return SOP(meta=meta, intent=intent, steps=steps)


def _fingerprint(steps: list[SOPStep]) -> tuple[str, ...]:
    return tuple(s.action for s in steps)


def _score(sop: SOP, query: Optional[str]) -> float:
    if not query:
        return 0.0
    q = query.lower()
    q_terms = set(re.findall(r"[\w\u4e00-\u9fff]+", q))
    tags_lc = {t.lower() for t in sop.meta.tags}
    tag_terms = set()
    for t in tags_lc:
        tag_terms.update(re.findall(r"[\w\u4e00-\u9fff]+", t))
    overlap = len(q_terms & tag_terms)
    name_hit = 1.0 if any(term in sop.meta.name.lower() for term in q_terms) else 0.0
    return overlap * 2.0 + name_hit


def _detect_conflicts(new_actions: tuple[str, ...], existing: list[SOP]) -> list[str]:
    conflicts: list[str] = []
    new_set = set(new_actions)
    for other in existing:
        other_set = {s.action for s in other.steps}
        for a, b in MUTUALLY_EXCLUSIVE_ACTION_PAIRS:
            if (a in new_set and b in other_set) or (b in new_set and a in other_set):
                conflicts.append(other.meta.id)
                break
    return conflicts


def list_(user_id: str) -> list[SOPMeta]:
    """List SOP metadata for `user_id`, sorted by updated desc."""
    d = _user_dir(user_id)
    if not d.exists():
        return []
    metas: list[SOPMeta] = []
    for path in d.glob("*.md"):
        try:
            metas.append(_deserialize(path).meta)
        except Exception:
            continue
    metas.sort(key=lambda m: m.updated, reverse=True)
    return metas


def get(user_id: str, sop_id: str) -> SOP:
    d = _user_dir(user_id)
    path = (d / f"{sop_id}.md").resolve()
    path.relative_to(d.resolve())
    if not path.exists():
        raise FileNotFoundError(f"SOP not found: {sop_id}")
    return _deserialize(path)


def _load_all(user_id: str) -> list[SOP]:
    d = _user_dir(user_id)
    if not d.exists():
        return []
    sops: list[SOP] = []
    for path in d.glob("*.md"):
        try:
            sops.append(_deserialize(path))
        except Exception:
            continue
    return sops


def write(user_id: str, candidate_or_sop) -> Path:
    """Write a SOP (from SOPCandidate or SOP), performing dedup + conflict detection.

    Returns the file path of the (new or updated) SOP.
    """
    d = _ensure_dir(user_id)
    from .models import SOPCandidate

    if isinstance(candidate_or_sop, SOPCandidate):
        cand = candidate_or_sop
        sop = SOP(
            meta=SOPMeta(
                id=str(uuid.uuid4()),
                name=cand.name,
                tags=cand.tags,
                source_trace_ids=cand.source_trace_ids,
                confidence=cand.confidence,
            ),
            intent=cand.intent,
            steps=cand.steps,
        )
    elif isinstance(candidate_or_sop, SOP):
        sop = candidate_or_sop
    else:
        raise TypeError("write() accepts SOPCandidate or SOP")

    if not sop.meta.id or not sop.meta.name:
        raise ValueError("missing required frontmatter fields")

    existing = _load_all(user_id)
    fp = _fingerprint(sop.steps)

    for other in existing:
        if _fingerprint(other.steps) != fp:
            continue
        other.meta.version += 1
        other.meta.updated = utcnow()
        merged = list({*other.meta.source_trace_ids, *sop.meta.source_trace_ids})
        other.meta.source_trace_ids = merged
        # Propagate the strictest safety status of the two SOPs.
        if not sop.meta.enabled or sop.meta.needs_review:
            other.meta.enabled = other.meta.enabled and sop.meta.enabled
            other.meta.needs_review = True
        out = d / f"{other.meta.id}.md"
        _atomic_write(out, _serialize(other))
        return out

    conflicts = _detect_conflicts(fp, existing)
    if conflicts:
        sop.meta.conflict_with = list({*sop.meta.conflict_with, *conflicts})
        sop.meta.needs_review = True
        for other in existing:
            if other.meta.id in conflicts:
                other.meta.conflict_with = list({*other.meta.conflict_with, sop.meta.id})
                other.meta.needs_review = True
                _atomic_write(d / f"{other.meta.id}.md", _serialize(other))

    out = d / f"{sop.meta.id}.md"
    _atomic_write(out, _serialize(sop))
    return out


def retrieve(
    user_id: str,
    query: Optional[str] = None,
    k: int = 3,
    filters: Optional[dict] = None,
    include_disabled: bool = False,
) -> list[SOP]:
    sops = _load_all(user_id)
    if not include_disabled:
        sops = [s for s in sops if s.meta.enabled and not s.meta.needs_review]
    if filters and "tags" in filters:
        want = {t.lower() for t in filters["tags"]}
        sops = [s for s in sops if want & {t.lower() for t in s.meta.tags}]
    if query:
        sops.sort(key=lambda s: (_score(s, query), s.meta.updated), reverse=True)
    else:
        sops.sort(key=lambda s: s.meta.updated, reverse=True)
    return sops[: max(0, k)]
