"""Analysis pipeline: deterministic rules first, optional AI review and source retrieval second."""
from __future__ import annotations

from collections import Counter
from typing import Optional

import httpx

from .analyzers.brand import analyze_brand
from .analyzers.factuality import analyze_factuality
from .analyzers.intent import analyze_intent
from .analyzers.quality import analyze_quality
from .analyzers.text_utils import sha256, stats
from .llm.providers import LLMError, get_provider
from .llm.semantic import run_semantic_review
from .llm.verify import search_configured, verify_claims
from .models import AIStatus, AnalyzeRequest, AnalyzeResponse, Finding, Summary, TextStats
from .analyzers.common import finding

WEIGHTS = {"high": 6, "medium": 3, "low": 1, "info": 0}
AI_CHECKS = [
    "Repeated ideas expressed in different wording (rules only catch shared vocabulary)",
    "Weak explanations and missing context",
    "Claims implied without explicit numbers or keywords",
    "Judging whether the draft actually answers the audience's questions (rules use cue words)",
    "Applying free-text brand guidelines (rules only apply explicit avoid lists, term mappings, tone and the example-style comparison)",
]

LIMITATIONS = [
    "Factuality findings identify claims that need checking. Unless a source is attached, nothing has been verified, and a flag does not mean the claim is false.",
    "Search-intent findings are editorial heuristics based on your brief. They are not search-engine ranking factors and do not predict or guarantee rankings.",
    "Brand-voice checks apply only the rules you supplied; nothing is assumed about your brand.",
    "Rule-based checks match patterns and can produce false positives (for example, a ‘vague’ word used deliberately). Review each finding before accepting it.",
    "The quality score is a simple issue-density index computed from these findings, not an absolute measure of quality.",
]


def _score(findings: list[Finding], words: int) -> tuple[int, str]:
    weighted = sum(WEIGHTS[f.severity] for f in findings)
    density = weighted / max(1.0, words / 100)
    score = round(100 / (1 + density / 10))
    return score, (
        f"Issue-density index: weighted findings (high 6, medium 3, low 1) = {weighted}, "
        f"{density:.1f} per 100 words; score = 100 ÷ (1 + density ÷ 10). Higher means fewer issues relative to length."
    )


def _headline(score: int, sev: Counter[str]) -> str:
    if score >= 85 and sev["high"] == 0:
        return "Few issues found. Review the remaining suggestions before publishing."
    if sev["high"]:
        return f"{sev['high']} high-severity issue(s) need attention before publishing."
    if score >= 60:
        return "Moderate number of issues. Mostly clarity and support improvements."
    return "Many issues relative to length. Prioritise high and medium findings."


def _dedupe(rule_findings: list[Finding], ai_findings: list[Finding]) -> list[Finding]:
    keep = []
    for a in ai_findings:
        assert a.evidence
        dup = any(
            r.category == a.category and r.evidence and r.evidence.start <= a.evidence.start and a.evidence.end <= r.evidence.end
            for r in rule_findings
        )
        if not dup:
            keep.append(a)
    return keep


async def analyze(req: AnalyzeRequest, transport: Optional[httpx.AsyncBaseTransport] = None) -> AnalyzeResponse:
    text = req.text
    st = stats(text)
    findings: list[Finding] = []
    findings += analyze_factuality(text)
    findings += analyze_quality(text)
    findings += analyze_intent(text, req.intent)
    findings += analyze_brand(text, req.brand)

    if st["words"] < 50:
        findings.append(
            finding(
                text, category="quality", rule="short_content", title="Very short content",
                severity="info", confidence="high",
                explanation=f"The text has {st['words']} words. Repetition, completeness and style checks are less meaningful on very short content.",
                note="Analyze the full draft for a more complete review.", evidence_note=f"Document length: {st['words']} words.",
            )
        )

    provider, reason = get_provider(transport)
    if not req.use_ai:
        ai = AIStatus(enabled=provider is not None, provider=getattr(provider, "name", "none"), status="skipped", message="AI review was turned off for this run. Results are rule-based only.", checks_requiring_ai=AI_CHECKS)
    elif provider is None:
        ai = AIStatus(enabled=False, provider="none", status="disabled", message=reason + " Showing rule-based results only.", checks_requiring_ai=AI_CHECKS)
    else:
        try:
            ai_findings, questions, discarded = await run_semantic_review(provider, text, req.intent, req.brand)
            ai_findings = _dedupe(findings, ai_findings)
            for q in questions:
                ai_findings.append(
                    finding(
                        text, category="intent", rule="ai_unanswered_question", title=f"Likely question not answered: {q}",
                        severity="low", confidence="low", origin="ai",
                        explanation="AI assessment of a question the target audience is likely to have that the draft does not answer.",
                        note=f"Answer it in the body or an FAQ: “{q}”.", evidence_note="Identified by AI review; no specific passage.",
                    )
                )
            findings += ai_findings
            msg = f"AI review added {len(ai_findings)} finding(s)."
            if discarded:
                msg += f" {discarded} AI finding(s) were discarded because their quoted evidence was not found verbatim in your text."
            ai = AIStatus(enabled=True, provider=provider.name, status="ok", message=msg)
        except LLMError as e:
            ai = AIStatus(enabled=True, provider=provider.name, status="error", message=f"AI review failed: {e} Showing rule-based results only.", checks_requiring_ai=AI_CHECKS)

    ok, sp_name = search_configured()
    if req.verify_sources and ok:
        checked, errors = await verify_claims(findings, provider if ai.status == "ok" else None, transport)
        verification_provider = f"{sp_name} ({checked} claim(s) searched" + (f"; errors: {'; '.join(errors)}" if errors else "") + ")"
    else:
        verification_provider = "none: claims are labelled “Needs verification”" if not ok else "skipped for this run"

    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (f.evidence.start if f.evidence else 10**9, order[f.severity]))
    # ensure ids unique
    seen: Counter[str] = Counter()
    for f in findings:
        seen[f.id] += 1
        if seen[f.id] > 1:
            f.id = f"{f.id}-{seen[f.id]}"

    sev = Counter(f.severity for f in findings)
    score, expl = _score(findings, st["words"])
    summary = Summary(
        score=score,
        score_explanation=expl,
        by_category=dict(Counter(f.category for f in findings)),
        by_severity=dict(sev),
        by_origin=dict(Counter(f.origin for f in findings)),
        headline=_headline(score, sev),
    )
    return AnalyzeResponse(
        findings=findings, summary=summary, stats=TextStats(**st), ai=ai,
        verification_provider=verification_provider, limitations=LIMITATIONS, text_sha256=sha256(text),
    )
