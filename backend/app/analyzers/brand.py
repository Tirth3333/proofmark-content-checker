"""Brand-voice checks. Every rule here comes from what the user supplied:
avoid-lists, preferred-term mappings, the tone they chose, the "no unsupported claims"
toggle, explicit "avoid/don't use" lines in their guidelines, and their example content.
Nothing is invented beyond the documented interpretation of each tone option.
"""
from __future__ import annotations

import re
import statistics as st

from ..models import BrandBrief, Finding
from .common import finding
from .quality import GUARANTEES, SUPERLATIVES, _phrase_regex
from .text_utils import match_case, sentence_at, sentences, words

TONE_RULES: dict[str, list[tuple[str, str | None, str]]] = {
    # pattern, replacement (None = advisory), reason
    "formal": [
        (r"\b(?:gonna|wanna|gotta|kinda|sorta)\b", None, "slang"),
        (r"\b(?:awesome|super|cool|crazy|insane|totally|stuff|guys)\b", None, "informal vocabulary"),
        (r"\b(?:can't|won't|don't|doesn't|isn't|aren't|it's|you're|we're|they're|i'm|you'll|we'll|didn't|shouldn't|wouldn't|couldn't)\b", "__expand__", "contraction"),
        (r"!+", ".", "exclamation mark"),
    ],
    "conversational": [
        (r"\b(?:herein|hereby|aforementioned|pursuant to|heretofore|whereby|thereof|henceforth)\b", None, "legalistic wording"),
        (r"\butili[sz]e[sd]?\b", "use", "stiff wording"),
        (r"\bcommence[sd]?\b", "start", "stiff wording"),
        (r"\bendeavou?r\b", "try", "stiff wording"),
        (r"\bprior to\b", "before", "stiff wording"),
    ],
    "plain": [
        (r"\butili[sz](?:e|es|ed|ing|ation)\b", "use", "complex word"),
        (r"\bfacilitate[sd]?\b", "help", "complex word"),
        (r"\bleverag(?:e|es|ed|ing)\b", "use", "jargon"),
        (r"\bsynerg(?:y|ies|istic)\b", None, "jargon"),
        (r"\bparadigm(?: shift)?\b", None, "jargon"),
        (r"\boptimi[sz]ation\b", None, "jargon (explain what improves)"),
        (r"\bin order to\b", "to", "wordy"),
        (r"\bapproximately\b", "about", "complex word"),
        (r"\bcommence[sd]?\b", "start", "complex word"),
    ],
    "confident": [
        (r"\b(?:maybe|perhaps|possibly|might possibly|we think|we believe|we feel|hopefully|sort of|kind of|i guess)\b", None, "hedging"),
        (r"\b[A-Z]{5,}\b", None, "shouting (all caps)"),
        (r"!{2,}", "!", "repeated exclamation marks"),
    ],
}

CONTRACTIONS = {
    "can't": "cannot", "won't": "will not", "don't": "do not", "doesn't": "does not", "isn't": "is not",
    "aren't": "are not", "it's": "it is", "you're": "you are", "we're": "we are", "they're": "they are",
    "i'm": "I am", "you'll": "you will", "we'll": "we will", "didn't": "did not", "shouldn't": "should not",
    "wouldn't": "would not", "couldn't": "could not",
}


def parse_preferred(rules: str) -> list[tuple[str, str]]:
    """Return (avoid, preferred) pairs from lines like
    'use customers instead of clients', 'clients -> customers', 'clients => customers', 'clients: customers'."""
    pairs = []
    for line in rules.splitlines():
        line = line.strip().strip("-•* ").strip()
        if not line:
            continue
        m = re.match(r"(?i)^use\s+[\"“']?(.+?)[\"”']?\s+(?:instead of|not|rather than)\s+[\"“']?(.+?)[\"”']?\.?$", line)
        if m:
            pairs.append((m.group(2).strip(), m.group(1).strip()))
            continue
        m = re.match(r"^[\"“']?(.+?)[\"”']?\s*(?:->|=>|→|:)\s*[\"“']?(.+?)[\"”']?$", line)
        if m:
            pairs.append((m.group(1).strip(), m.group(2).strip()))
    return [(a, b) for a, b in pairs if a and b and a.lower() != b.lower()]


def parse_guideline_avoids(guidelines: str) -> list[str]:
    """Extract explicit avoid rules from free-text guidelines, e.g.
    'Avoid: synergy, rockstar' or 'Never use “cheap”' or 'Don't say "guys"'."""
    terms: list[str] = []
    for line in guidelines.splitlines():
        m = re.match(r"(?i)^\s*[-•*]?\s*(?:avoid|do not use|don't use|never use|never say|don't say|do not say|banned(?: words)?)\s*[:\-]?\s*(.+)$", line)
        if not m:
            continue
        body = m.group(1)
        quoted = re.findall(r"[\"“']([^\"”']+)[\"”']", body)
        if quoted:
            terms += quoted
        else:
            terms += [t.strip(" .") for t in re.split(r",|;|\bor\b|\band\b", body) if t.strip(" .")]
    return [t for t in terms if 0 < len(t) <= 40]


def _style(text: str) -> dict[str, float]:
    sents = [s for s in sentences(text) if len(words(s.text)) >= 3]
    if not sents:
        return {}
    lens = [len(words(s.text)) for s in sents]
    wc = max(1, sum(lens))
    lower = text.lower()
    return {
        "avg_sentence_words": st.mean(lens),
        "contractions_per_100w": 100 * len(re.findall(r"\b\w+'(?:t|s|re|ll|ve|m|d)\b", lower)) / wc,
        "exclamations_per_10s": 10 * text.count("!") / len(sents),
        "second_person_per_100w": 100 * len(re.findall(r"\byou(?:r|rs|'re|'ll)?\b", lower)) / wc,
        "first_person_plural_per_100w": 100 * len(re.findall(r"\b(?:we|our|us)\b", lower)) / wc,
    }


def analyze_brand(text: str, brief: BrandBrief) -> list[Finding]:
    out: list[Finding] = []
    sents = sentences(text)

    # 1. Preferred terminology
    for avoid, preferred in parse_preferred(brief.preferred_terms):
        for m in _phrase_regex(avoid).finditer(text):
            out.append(
                finding(
                    text, category="brand", rule="preferred_term", title="Use preferred terminology",
                    severity="medium", confidence="high",
                    explanation=f"Your terminology rules say to use “{preferred}” instead of “{avoid}”.",
                    note=f"Replace with “{preferred}”.",
                    start=m.start(), end=m.end(), replacement=match_case(m.group(0), preferred),
                )
            )
    mapped = {a.lower() for a, _ in parse_preferred(brief.preferred_terms)}

    # 2. Avoid list (explicit field + "avoid ..." lines in guidelines)
    avoid_terms = [t.strip() for t in brief.avoid_terms if t.strip()]
    from_guidelines = parse_guideline_avoids(brief.guidelines)
    for term, origin in [(t, "avoid list") for t in avoid_terms] + [(t, "brand guidelines") for t in from_guidelines]:
        if term.lower() in mapped:
            continue
        for m in _phrase_regex(term).finditer(text):
            out.append(
                finding(
                    text, category="brand", rule="avoid_term", title="Word or phrase your brand avoids",
                    severity="medium", confidence="high",
                    explanation=f"“{m.group(0)}” is on your {origin}.",
                    note="Rephrase without this term. (No preferred replacement was supplied.)",
                    start=m.start(), end=m.end(),
                )
            )

    # 3. Tone
    for pat, repl, reason in TONE_RULES.get(brief.tone, []):
        for m in re.finditer(pat, text, re.I if "A-Z" not in pat else 0):
            r = None
            if repl == "__expand__":
                r = match_case(m.group(0), CONTRACTIONS.get(m.group(0).lower().replace("’", "'"), m.group(0)))
            elif repl is not None:
                r = match_case(m.group(0), repl) if m.group(0)[:1].isalpha() else repl
            out.append(
                finding(
                    text, category="brand", rule=f"tone_{brief.tone}", title=f"Off-tone for “{brief.tone}” voice",
                    severity="low", confidence="medium",
                    explanation=f"You chose a {brief.tone} tone. “{m.group(0)}” is {reason}, which reads as inconsistent with that tone.",
                    note=(f"Replace with “{r}”." if r else "Rephrase in the chosen tone."),
                    start=m.start(), end=m.end(), replacement=r,
                )
            )

    # 4. Unsupported promises (only when the user enabled this rule)
    if brief.forbid_unsupported_claims:
        pats = [_phrase_regex(p) for p in SUPERLATIVES] + [re.compile(r"\b" + g + r"(?!\w)", re.I) for g in GUARANTEES]
        seen = set()
        for p in pats:
            for m in p.finditer(text):
                s = sentence_at(sents, m.start())
                if not s or s.start in seen or re.search(r"\d|source|according to|https?://", s.text, re.I):
                    continue
                seen.add(s.start)
                out.append(
                    finding(
                        text, category="brand", rule="unsupported_promise", title="Breaks your no-unsupported-claims rule",
                        severity="high", confidence="medium",
                        explanation=f"Your brand rules prohibit unsupported promises or claims. “{m.group(0)}” makes one and the sentence offers no evidence.",
                        note="Rewrite as a specific, verifiable statement, or add the evidence.",
                        start=s.start, end=s.end,
                    )
                )

    # 5. Stylometric comparison with the example content
    if brief.example_content.strip() and len(words(brief.example_content)) >= 40:
        ref, cur = _style(brief.example_content), _style(text)
        if ref and cur:
            diffs = []
            if cur["avg_sentence_words"] > ref["avg_sentence_words"] * 1.5 and cur["avg_sentence_words"] - ref["avg_sentence_words"] > 6:
                diffs.append(("avg_sentence_words", f"sentences average {cur['avg_sentence_words']:.0f} words vs {ref['avg_sentence_words']:.0f} in your example"))
            if ref["contractions_per_100w"] >= 1 and cur["contractions_per_100w"] < ref["contractions_per_100w"] / 3:
                diffs.append(("contractions", "the example uses contractions; the draft rarely does"))
            if ref["contractions_per_100w"] < 0.3 and cur["contractions_per_100w"] > 1.5:
                diffs.append(("contractions", "the draft uses contractions; the example does not"))
            if cur["exclamations_per_10s"] > ref["exclamations_per_10s"] + 1:
                diffs.append(("exclamations", "the draft uses noticeably more exclamation marks"))
            if ref["second_person_per_100w"] >= 2 and cur["second_person_per_100w"] < ref["second_person_per_100w"] / 3:
                diffs.append(("you", "the example addresses the reader as “you”; the draft rarely does"))
            for key, desc in diffs:
                ev = None
                if key == "avg_sentence_words":
                    ev = max(sents, key=lambda s: len(words(s.text)), default=None)
                elif key == "exclamations":
                    ev = next((s for s in sents if "!" in s.text), None)
                out.append(
                    finding(
                        text, category="brand", rule="style_drift", title="Style differs from your example content",
                        severity="low", confidence="low",
                        explanation=f"Measured comparison with your example: {desc}.",
                        note="Revise toward the rhythm of your example content.",
                        start=ev.start if ev else None, end=ev.end if ev else None,
                        evidence_note="" if ev else "Document-level style measurement.",
                    )
                )
    return out
