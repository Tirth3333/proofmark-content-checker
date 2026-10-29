"""Deterministic factual-claim detection.

This module only *identifies* sentences that make checkable claims. It never decides
that a claim is true or false. Every claim starts as "needs_verification"; only the
optional source-retrieval layer can attach sources, and even then a claim is never
marked false merely because no source was found.
"""
from __future__ import annotations

import re

from ..models import Finding, Verification
from .common import finding
from .text_utils import Segment, is_heading, sentences

PATTERNS: dict[str, re.Pattern[str]] = {
    "statistic": re.compile(
        r"\b\d+(?:[.,]\d+)?\s?(?:%|percent\b|per cent\b)|"
        r"\b\d+(?:\.\d+)?\s?(?:x|times)\s+(?:more|faster|higher|better|less|lower)\b|"
        r"[$€£₹]\s?\d[\d,.]*(?:\s?(?:k|m|bn|million|billion|trillion|crore|lakh))?|"
        r"\b\d[\d,.]*\s+(?:million|billion|trillion|thousand|crore|lakh)\b|"
        r"\b(?:doubled|tripled|quadrupled|halved)\b|"
        r"\b(?:one|two|three|four|nine) (?:in|out of) (?:two|three|four|five|ten)\b|"
        r"\b\d{2,}[\d,]*\s+(?:users|customers|people|companies|businesses|visitors|downloads|websites|marketers|respondents)\b",
        re.I,
    ),
    "date": re.compile(
        r"\b(?:in|since|by|from|until|as of|founded in|launched in|released in)\s+(?:19|20)\d{2}\b|"
        r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:19|20)\d{2}\b|"
        r"\b(?:19|20)\d{2}\b",
        re.I,
    ),
    "study_or_research": re.compile(
        r"\b(?:stud(?:y|ies)|research(?:ers)?|survey(?:ed)?|report(?:ed|s)?|according to|scientists?|"
        r"data (?:shows?|suggests?)|statistics (?:show|prove)|experts? (?:say|agree|recommend)|"
        r"clinical(?:ly)?|peer[- ]reviewed|meta-analysis|published in)\b",
        re.I,
    ),
    "product_spec": re.compile(
        r"\b\d+(?:\.\d+)?\s?(?:GB|TB|MB|GHz|MHz|mAh|Wh|W|kW|mph|km/h|kph|km|kg|g|mg|ml|L|fps|Mbps|Gbps|inch(?:es)?|\"|hours? of battery|MP|nm)\b|"
        r"\bversion\s+\d+(?:\.\d+)+\b|\bv\d+\.\d+\b",
        re.I,
    ),
    "absolute": re.compile(
        r"\b(?:always|never|every(?:one|body)?|no one|nobody|all (?:users|people|businesses|experts|customers)|"
        r"proven|scientifically|clinically proven|undeniabl[ey]|the fact is|it is a fact|cures?|eliminates?|"
        r"completely (?:safe|removes)|impossible)\b",
        re.I,
    ),
    "named_ranking": re.compile(
        r"\bthe\s+(?:world'?s\s+|country'?s\s+|industry'?s\s+)?(?:largest|biggest|oldest|most popular|fastest[- ]growing|top[- ]rated|leading)\b|"
        r"\bthe\s+first\s+(?:to|company|brand|platform|tool|app|product|business|firm|organi[sz]ation|person|team|country)\b",
        re.I,
    ),
}

ATTRIBUTION = re.compile(
    r"https?://\S+|\bsource:|\[\d+\]|\(\s*[A-Z][A-Za-z&.\- ]+,?\s*(?:19|20)\d{2}\s*\)|"
    r"according to (?:the )?(?:[A-Z][\w&.\-]+(?:\s+[A-Z][\w&.\-]+)*)",
)
VAGUE_ATTRIBUTION = re.compile(r"\b(?:stud(?:y|ies) (?:show|prove|suggest)s?|research (?:shows|proves|suggests)|experts (?:say|agree)|scientists (?:say|agree)|statistics (?:show|prove))\b", re.I)

SOURCE_TYPES = {
    "statistic": "Original dataset or primary report (government statistics office, peer-reviewed study, or the publisher's methodology page)",
    "date": "Primary record of the event (official press release, company filing, archived announcement)",
    "study_or_research": "The study itself (journal article with DOI, or the publishing institution's page), not a secondary blog summary",
    "product_spec": "Manufacturer's official specification sheet or documentation for the exact model/version",
    "absolute": "Systematic review or authoritative body; absolute wording usually needs softening rather than a source",
    "named_ranking": "Independent ranking or market-share report naming the methodology and date",
}

SEVERITY = {"statistic": 3, "study_or_research": 3, "product_spec": 2, "named_ranking": 2, "date": 1, "absolute": 2}
LABELS = {
    "statistic": "statistic",
    "date": "date",
    "study_or_research": "research reference",
    "product_spec": "product specification",
    "absolute": "absolute statement",
    "named_ranking": "ranking claim",
}


def classify(sentence: str) -> list[str]:
    types = []
    for name, pat in PATTERNS.items():
        if name == "date":
            # bare years only count when not obviously a copyright/heading line
            if not pat.search(sentence) or re.search(r"©|copyright", sentence, re.I):
                continue
        elif not pat.search(sentence):
            continue
        types.append(name)
    return types


def _claim_span(s: Segment, types: list[str]) -> tuple[int, int]:
    return s.start, s.end


def analyze_factuality(text: str) -> list[Finding]:
    out: list[Finding] = []
    for s in sentences(text):
        if is_heading(s) and not re.search(r"\d", s.text):
            continue
        types = classify(s.text)
        if not types:
            continue
        has_attr = bool(ATTRIBUTION.search(s.text))
        vague_attr = bool(VAGUE_ATTRIBUTION.search(s.text))
        score = max(SEVERITY[t] for t in types)
        if vague_attr and not has_attr:
            score = 3
        if has_attr:
            score -= 1
        severity = {3: "high", 2: "medium", 1: "low"}.get(max(score, 0), "low")
        if types in (["date"], ["absolute"]):
            severity = "low"
        specific = any(t in types for t in ("statistic", "product_spec")) or (types != ["absolute"] and "date" in types)
        confidence = "high" if specific else ("medium" if "study_or_research" in types else "low")

        reasons = []
        if "statistic" in types:
            reasons.append("it states a number or statistic that readers will take as fact")
        if "study_or_research" in types:
            reasons.append("it refers to research or experts" + (" without naming them" if not has_attr else ""))
        if "date" in types:
            reasons.append("it ties a fact to a specific date or year")
        if "product_spec" in types:
            reasons.append("it states a product specification that may differ by model or version")
        if "absolute" in types:
            reasons.append("it uses absolute wording (always/never/proven) that a single counter-example would disprove")
        if "named_ranking" in types:
            reasons.append("it claims a ranking or ‘first/largest’ position")
        attr_note = (
            " The sentence includes an attribution, but the attribution itself has not been checked."
            if has_attr
            else " No source is cited in the sentence."
        )
        note = "Add a citation to a primary source next to this claim" + (
            ", or soften the absolute wording." if "absolute" in types else "."
        )
        out.append(
            finding(
                text,
                category="factuality",
                rule="claim_" + types[0],
                title="Needs verification: " + ", ".join(LABELS[t] for t in types),
                severity=severity,
                confidence=confidence,
                explanation="Flagged because " + "; ".join(reasons) + "." + attr_note,
                note=note,
                start=_claim_span(s, types)[0],
                end=_claim_span(s, types)[1],
                verification=Verification(
                    status="needs_verification",
                    claim_types=types,
                    suggested_source_types=[SOURCE_TYPES[t] for t in types],
                    note="Not checked against any source. This flag means the claim should be verified, not that it is false.",
                ),
            )
        )
    return out
