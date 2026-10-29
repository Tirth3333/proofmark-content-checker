from __future__ import annotations

from typing import Optional

from ..models import Finding, Span, Suggestion, Verification
from .text_utils import stable_id


def span(text: str, start: int, end: int) -> Span:
    return Span(start=start, end=end, text=text[start:end])


def finding(
    text: str,
    *,
    category: str,
    rule: str,
    title: str,
    severity: str,
    confidence: str,
    explanation: str,
    note: str,
    start: Optional[int] = None,
    end: Optional[int] = None,
    replacement: Optional[str] = None,
    edit: Optional[tuple[int, int, str]] = None,
    evidence_note: str = "",
    related: Optional[list[Span]] = None,
    verification: Optional[Verification] = None,
    origin: str = "rule",
) -> Finding:
    """Build a Finding. If `edit` is given, the evidence span is the edit range so that
    accepting the suggestion replaces exactly the evidence text and nothing else."""
    if edit is not None:
        start, end, replacement = edit
    ev = span(text, start, end) if start is not None and end is not None else None
    return Finding(
        id=stable_id(category, rule, start, end, title, evidence_note),
        category=category,  # type: ignore[arg-type]
        rule=rule,
        title=title,
        severity=severity,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        origin=origin,  # type: ignore[arg-type]
        evidence=ev,
        evidence_note=evidence_note,
        related=related or [],
        explanation=explanation,
        suggestion=Suggestion(note=note, replacement=replacement),
        verification=verification,
    )
