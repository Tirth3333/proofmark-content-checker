"""Deterministic writing-quality rules.

Each rule is transparent: the explanation names the pattern that fired. Confidence is a
fixed property of the rule (how reliably the pattern indicates a real problem), not a
model output.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from ..models import Finding
from .common import finding, span
from .text_utils import (
    STOPWORDS,
    Segment,
    content_stems,
    is_heading,
    match_case,
    norm,
    paragraphs,
    removal_edit,
    sentence_at,
    sentences,
    words,
)

# ---------------------------------------------------------------- lexicons
# phrase -> (replacement or None for advisory, note)
FILLER: dict[str, tuple[str | None, str]] = {
    "in order to": ("to", "“In order to” can almost always be shortened to “to”."),
    "due to the fact that": ("because", "Use “because”."),
    "at this point in time": ("now", "Use “now”."),
    "in the event that": ("if", "Use “if”."),
    "for the purpose of": ("to", "Use “to”."),
    "has the ability to": ("can", "Use “can”."),
    "it is important to note that": ("", "The sentence works without this preamble."),
    "it should be noted that": ("", "The sentence works without this preamble."),
    "needless to say": ("", "If it is needless to say, it can be cut."),
    "at the end of the day": ("", "Cliché filler; cut it or state the actual outcome."),
    "when it comes to": ("for", "Usually replaceable with “for” or “with”."),
    "in today's fast-paced world": ("", "Generic opener that adds no information."),
    "in today’s fast-paced world": ("", "Generic opener that adds no information."),
    "in today's digital age": ("", "Generic opener that adds no information."),
    "basically": ("", "Filler word; removing it does not change the meaning."),
    "actually": ("", "Filler word in most contexts."),
    "literally": ("", "Filler/intensifier; rarely meant literally."),
    "very": ("", "Weak intensifier; prefer a more precise word."),
    "really": ("", "Weak intensifier; prefer a more precise word."),
    "truly": ("", "Weak intensifier."),
}

VAGUE: dict[str, str] = {
    "a lot of": "Quantify it (a number, a percentage or a named group).",
    "lots of": "Quantify it.",
    "many people": "Say who, and how many, or cite where this comes from.",
    "some people": "Say who these people are.",
    "some experts": "Name the experts or the organisation.",
    "experts agree": "Name the experts and link their statement.",
    "various": "List the specific items instead.",
    "numerous": "Give the actual number.",
    "a number of": "Give the actual number.",
    "things": "Name the specific things.",
    "stuff": "Name the specific items.",
    "kind of": "Hedge that weakens the statement; be specific.",
    "sort of": "Hedge that weakens the statement; be specific.",
    "somewhat": "Hedge; state the degree precisely.",
    "in many ways": "Name the ways.",
    "and so on": "Complete the list or drop the trailing filler.",
    "and more": "Complete the list or say what “more” includes.",
    "etc.": "Complete the list or drop “etc.”.",
    "it is said that": "Say who said it.",
    "it is believed that": "Say who believes it and on what evidence.",
    "significantly": "Quantify the change.",
    "dramatically": "Quantify the change.",
    "huge": "Quantify it.",
    "massive": "Quantify it.",
}

SUPERLATIVES = [
    "the best", "best-in-class", "best in class", "#1", "number one", "world-class", "world class",
    "industry-leading", "industry leading", "market-leading", "leading", "unmatched", "unparalleled",
    "unbeatable", "revolutionary", "game-changing", "game changing", "cutting-edge", "state-of-the-art",
    "the most advanced", "the fastest", "the cheapest", "the easiest", "the only", "ultimate", "perfect",
    "flawless", "second to none",
]

GUARANTEES = [
    r"guarantee[sd]?", r"100\s?%\s+(?:guaranteed|effective|accurate|safe|success)", r"risk[- ]free",
    r"never fails?", r"always works", r"instant results?", r"overnight (?:success|results)",
    r"will (?:double|triple|skyrocket|explode|10x)", r"proven to (?:work|increase|boost|grow)",
    r"(?:ensures?|ensuring) (?:success|results|top rankings?|#1 rankings?)", r"no risk",
    r"(?:rank|ranking) #?1 on google", r"results in (?:days|hours)",
]

PLACEHOLDERS = re.compile(r"\b(?:TODO|TBD|TK|lorem ipsum|coming soon|\[insert[^\]]*\]|xx+)\b|\.\.\.$", re.I | re.M)
NUMERIC_SUPPORT = re.compile(r"\d|according to|source:|https?://|\(\d{4}\)|study|survey|report", re.I)
ACRONYM = re.compile(r"\b[A-Z]{2,6}s?\b")
COMMON_ACRONYMS = {
    "AI", "SEO", "URL", "FAQ", "USA", "US", "UK", "EU", "PDF", "API", "CEO", "HTML", "CSS", "OK", "TV",
    "PM", "AM", "ID", "PC", "IT", "HR", "CTA", "B2B", "B2C", "FAQS", "USD", "INR", "GB", "MB", "KB", "TODO", "TBD",
}


def _phrase_regex(phrase: str) -> re.Pattern[str]:
    esc = re.escape(phrase)
    left = r"(?<![\w#])" if phrase[0].isalnum() or phrase[0] == "#" else ""
    right = r"(?![\w])" if phrase[-1].isalnum() else ""
    return re.compile(left + esc + right, re.I)


# ---------------------------------------------------------------- rules
def filler_rule(text: str) -> list[Finding]:
    out = []
    taken: list[tuple[int, int]] = []
    for phrase, (repl, note) in sorted(FILLER.items(), key=lambda kv: -len(kv[0])):
        for m in _phrase_regex(phrase).finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append((m.start(), m.end()))
            if repl == "":
                edit = removal_edit(text, m.start(), m.end())
            else:
                edit = (m.start(), m.end(), match_case(m.group(0), repl))
            out.append(
                finding(
                    text, category="quality", rule="filler", title="Filler language",
                    severity="low", confidence="high",
                    explanation=f"Rule match: “{m.group(0)}” is on the filler/wordiness list. {note}",
                    note="Shorten: " + (f"replace with “{repl}”." if repl else "remove the phrase."),
                    edit=edit,
                )
            )
    return out


def vague_rule(text: str) -> list[Finding]:
    out = []
    for phrase, note in VAGUE.items():
        for m in _phrase_regex(phrase).finditer(text):
            out.append(
                finding(
                    text, category="quality", rule="vague_language", title="Vague or ambiguous wording",
                    severity="medium" if phrase in ("experts agree", "some experts", "many people", "it is said that", "it is believed that") else "low",
                    confidence="medium",
                    explanation=f"Rule match: “{m.group(0)}” is a non-specific expression. Readers cannot tell what, who or how much is meant.",
                    note=note, start=m.start(), end=m.end(),
                )
            )
    return out


def superlative_rule(text: str, sents: list[Segment]) -> list[Finding]:
    out = []
    taken: list[tuple[int, int]] = []
    for phrase in sorted(SUPERLATIVES, key=len, reverse=True):
        for m in _phrase_regex(phrase).finditer(text):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            s = sentence_at(sents, m.start())
            if s is None:
                continue
            if phrase == "leading" and not re.search(r"\b(?:leading|the leading)\s+(?:provider|platform|brand|company|solution|tool|expert)", text[m.start() - 4 : m.end() + 20], re.I):
                continue
            rest = s.text.replace(m.group(0), "")
            if NUMERIC_SUPPORT.search(rest):
                continue  # some form of support is present in the same sentence
            taken.append((m.start(), m.end()))
            out.append(
                finding(
                    text, category="quality", rule="unsupported_superlative", title="Unsupported superlative",
                    severity="medium", confidence="medium",
                    explanation=f"“{m.group(0)}” makes a comparative claim, and the sentence gives no data, source or basis for it.",
                    note="Back the claim with evidence (benchmark, award, customer data) or replace it with a specific, verifiable benefit.",
                    start=m.start(), end=m.end(),
                    related=[s.span()],
                )
            )
    return out


def guarantee_rule(text: str, sents: list[Segment]) -> list[Finding]:
    out = []
    for pat in GUARANTEES:
        for m in re.finditer(r"\b" + pat + r"(?!\w)", text, re.I):
            s = sentence_at(sents, m.start())
            out.append(
                finding(
                    text, category="quality", rule="guaranteed_results", title="Guaranteed-results claim",
                    severity="high", confidence="high",
                    explanation=f"“{m.group(0)}” promises an outcome. Unless it is contractually backed and documented, such promises can mislead readers and create legal or compliance risk.",
                    note="Describe what the product or advice is designed to do and what results depend on, or link to the actual guarantee terms.",
                    start=m.start(), end=m.end(), related=[s.span()] if s else [],
                )
            )
    return out


def repeated_phrase_rule(text: str) -> list[Finding]:
    toks = words(text)
    normed = [norm(t.text) for t in toks]
    out = []
    claimed: set[int] = set()
    for n in (6, 5, 4, 3):
        grams: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for i in range(len(toks) - n + 1):
            g = tuple(normed[i : i + n])
            if sum(1 for w in g if w not in STOPWORDS) < 2:
                continue
            # don't span paragraph breaks
            if "\n\n" in text[toks[i].start : toks[i + n - 1].end]:
                continue
            grams[g].append(i)
        for g, idxs in grams.items():
            # non-overlapping occurrences
            occ: list[int] = []
            for i in idxs:
                if not occ or i >= occ[-1] + n:
                    occ.append(i)
            threshold = 2 if n >= 4 else 3
            if len(occ) < threshold:
                continue
            if any(i in claimed for i in occ):
                continue
            for i in occ:
                claimed.update(range(i, i + n))
            spans = [span(text, toks[i].start, toks[i + n - 1].end) for i in occ]
            phrase = spans[0].text
            out.append(
                finding(
                    text, category="quality", rule="repeated_phrase", title="Repeated phrase",
                    severity="medium" if len(occ) >= 3 else "low", confidence="high",
                    explanation=f"The phrase “{phrase}” appears {len(occ)} times. Repeating the same wording makes the text feel padded.",
                    note="Keep the strongest occurrence and rephrase or remove the others.",
                    start=spans[1].start, end=spans[1].end, related=[spans[0]] + spans[2:],
                )
            )
    return out


def repeated_word_rule(text: str, sents: list[Segment]) -> list[Finding]:
    out = []
    for s in sents:
        toks = [w for w in words(s.text) if norm(w.text) not in STOPWORDS and len(w.text) > 3]
        seen: dict[str, Segment] = {}
        for w in toks:
            k = norm(w.text)
            if k in seen:
                first = seen[k]
                out.append(
                    finding(
                        text, category="quality", rule="repeated_word", title="Word repeated in one sentence",
                        severity="low", confidence="medium",
                        explanation=f"“{w.text}” is used more than once in the same sentence.",
                        note="Use a synonym, a pronoun, or restructure the sentence.",
                        start=s.start + w.start, end=s.start + w.end,
                        related=[span(text, s.start + first.start, s.start + first.end)],
                    )
                )
                break  # one per sentence is enough
            seen[k] = w
    return out


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb)


def repeated_idea_rule(text: str, sents: list[Segment], paras: list[Segment]) -> list[Finding]:
    """Lexical-overlap check between sentences in DIFFERENT paragraphs.

    This catches restated ideas that reuse vocabulary. Paraphrased repetition with
    different wording needs the semantic (AI) check.
    """
    def para_idx(pos: int) -> int:
        for i, p in enumerate(paras):
            if p.start <= pos < p.end:
                return i
        return -1

    vecs = []
    for s in sents:
        if is_heading(s):
            vecs.append(None)
            continue
        cs = content_stems(s.text)
        vecs.append(Counter(cs) if len(set(cs)) >= 4 else None)
    out = []
    flagged: set[int] = set()
    for j in range(len(sents)):
        if vecs[j] is None or j in flagged:
            continue
        for i in range(j):
            if vecs[i] is None or (para_idx(sents[i].start) == para_idx(sents[j].start) and j - i < 2):
                continue
            sim = _cosine(vecs[i], vecs[j])
            if sim >= 0.6:
                flagged.add(j)
                edit = _sentence_removal(text, sents[j])
                out.append(
                    finding(
                        text, category="quality", rule="repeated_idea", title="Idea repeated",
                        severity="medium", confidence="medium" if sim < 0.8 else "high",
                        explanation=(
                            f"This sentence shares {round(sim * 100)}% of its key vocabulary (cosine similarity of content words) "
                            "with an earlier, non-adjacent sentence, so it likely restates the same point."
                        ),
                        note="Remove this restatement, or merge any new detail into the earlier sentence.",
                        edit=edit, related=[sents[i].span()],
                    )
                )
                break
    return out


def _sentence_removal(text: str, s: Segment) -> tuple[int, int, str]:
    start, end = s.start, s.end
    if end < len(text) and text[end] == " ":
        end += 1
    elif start > 0 and text[start - 1] == " ":
        start -= 1
    return start, end, ""


def long_sentence_rule(text: str, sents: list[Segment]) -> list[Finding]:
    out = []
    for s in sents:
        n = len(words(s.text))
        if n > 35:
            out.append(
                finding(
                    text, category="quality", rule="long_sentence", title="Hard-to-follow sentence",
                    severity="low", confidence="medium",
                    explanation=f"This sentence is {n} words long. Sentences over ~35 words are harder to follow, especially on mobile.",
                    note="Split it into two or three sentences, one idea each.",
                    start=s.start, end=s.end,
                )
            )
    return out


def acronym_rule(text: str) -> list[Finding]:
    out = []
    seen = set()
    for m in ACRONYM.finditer(text):
        a = m.group(0).rstrip("s") if m.group(0).endswith("s") and m.group(0)[:-1].isupper() else m.group(0)
        if a in COMMON_ACRONYMS or a in seen or len(a) < 2:
            continue
        seen.add(a)
        defined = re.search(r"\(\s*" + re.escape(a) + r"s?\s*\)", text) or re.search(re.escape(a) + r"\s*\(", text)
        if defined:
            continue
        out.append(
            finding(
                text, category="quality", rule="undefined_acronym", title="Acronym not defined",
                severity="low", confidence="medium",
                explanation=f"“{a}” is never spelled out. Readers outside your field may not know it.",
                note=f"Spell it out on first use, e.g. “Full Name ({a})”.",
                start=m.start(), end=m.start() + len(a),
            )
        )
    return out


def ambiguous_reference_rule(text: str, paras: list[Segment]) -> list[Finding]:
    out = []
    for p in paras:
        m = re.match(r"(?!It\s+(?:is|was)\s+(?:important|worth|crucial|essential|clear|true|likely|possible|easy|hard|difficult|common|often|not)\b)(This|That|These|Those|It)(?=\s+(?:is|are|was|were|means|meant|will|can|could|has|have|helps|makes|shows|matters|works)\b)", p.text)
        if m and p.start > 0 and not is_heading(p):
            out.append(
                finding(
                    text, category="quality", rule="ambiguous_reference", title="Unclear reference",
                    severity="low", confidence="low",
                    explanation=f"The paragraph opens with “{m.group(1)}” without saying what it refers to. After a paragraph break the referent is often unclear.",
                    note=f"Name the thing directly, e.g. “{m.group(1)} [approach/tool/result] …”.",
                    start=p.start + m.start(), end=p.start + m.end(),
                )
            )
    return out


def incomplete_rule(text: str, paras: list[Segment]) -> list[Finding]:
    out = []
    for m in PLACEHOLDERS.finditer(text):
        out.append(
            finding(
                text, category="quality", rule="placeholder", title="Placeholder or unfinished text",
                severity="high", confidence="high",
                explanation=f"“{m.group(0)}” looks like a placeholder or an unfinished thought.",
                note="Complete or remove this before publishing.",
                start=m.start(), end=m.end(),
            )
        )
    for i, p in enumerate(paras):
        if p.text.rstrip().endswith(":"):
            nxt = paras[i + 1].text if i + 1 < len(paras) else ""
            if not nxt or is_heading(paras[i + 1]) and not re.match(r"^\s*(?:[-*•]|\d+[.)])", nxt):
                out.append(
                    finding(
                        text, category="quality", rule="incomplete_explanation", title="Explanation stops short",
                        severity="medium", confidence="medium",
                        explanation="This paragraph introduces something with a colon, but no list or explanation follows.",
                        note="Add the items or explanation the colon promises.",
                        start=p.start, end=p.end,
                    )
                )
    if paras:
        last = paras[-1]
        if not is_heading(last) and not re.search(r"[.!?:\"”’)\]*]\s*$", last.text) and len(words(last.text)) >= 5:
            ls = sentences(text)[-1]
            out.append(
                finding(
                    text, category="quality", rule="incomplete_explanation", title="Text ends mid-sentence",
                    severity="high", confidence="medium",
                    explanation="The document ends without closing punctuation, so the final explanation appears to be cut off.",
                    note="Finish the final sentence and close the section (for example with next steps or a call to action).",
                    start=ls.start, end=ls.end,
                )
            )
    # "There are three ways..." followed by fewer list items/headings
    for m in re.finditer(r"\b(two|three|four|five|six|seven)\s+(ways|steps|reasons|tips|benefits|things)\b", text, re.I):
        n = ["two", "three", "four", "five", "six", "seven"].index(m.group(1).lower()) + 2
        after = text[m.end() :]
        nxt_heading = re.search(r"(?m)^#{1,4}\s", after)
        if nxt_heading:
            after = after[: nxt_heading.start()]
        items = re.findall(r"(?m)^\s*(?:[-*•]|\d+[.)]|#{2,4}\s|(?:First|Second|Third|Fourth|Fifth|Sixth|Seventh|Finally)\b)", after)
        if 0 < len(items) < n:
            out.append(
                finding(
                    text, category="quality", rule="incomplete_explanation", title="Promised list is incomplete",
                    severity="medium", confidence="low",
                    explanation=f"The text promises {m.group(1)} {m.group(2)}, but only {len(items)} list item(s)/sub-heading(s) follow.",
                    note=f"Add the missing {m.group(2)} or change the number.",
                    start=m.start(), end=m.end(),
                )
            )
    return out


TERM_VARIANTS = re.compile(r"\b([A-Za-z]{2,})[\s\-]([A-Za-z]{2,})\b|\b([A-Za-z]{4,})\b")


def terminology_rule(text: str) -> list[Finding]:
    """Same compound written different ways (e-mail/email, sign-up/sign up/signup)."""
    forms: dict[str, Counter[str]] = defaultdict(Counter)
    positions: dict[tuple[str, str], list[int]] = defaultdict(list)
    singles = Counter(norm(w.text) for w in words(text))
    for m in re.finditer(r"\b([A-Za-z]{1,})(-| )([A-Za-z]{2,})\b", text):
        a, sep, b = m.group(1), m.group(2), m.group(3)
        key = (a + b).lower()
        if key in singles or sep == "-":
            surface = m.group(0).lower()
            forms[key][surface] += 1
            positions[(key, surface)].append(m.start())
    # overlapping matches skipped by finditer: also scan with lookahead
    for m in re.finditer(r"(?=\b([A-Za-z]{1,}) ([A-Za-z]{2,})\b)", text):
        a, b = m.group(1), m.group(2)
        key = (a + b).lower()
        surface = f"{a} {b}".lower()
        if key in singles and m.start() not in positions[(key, surface)]:
            forms[key][surface] += 1
            positions[(key, surface)].append(m.start())
    for m in re.finditer(r"\b[A-Za-z]{4,}\b", text):
        key = m.group(0).lower()
        if key in forms:
            forms[key][key] += 1
            positions[(key, key)].append(m.start())
    out = []
    for key, c in forms.items():
        if len(c) < 2:
            continue
        top = max(c.values())
        preferred = sorted([f for f, n in c.items() if n == top], key=lambda f: ("-" in f or " " in f, f))[0]
        for surface, cnt in c.items():
            if surface == preferred:
                continue
            for pos in positions[(key, surface)]:
                orig = text[pos : pos + len(surface)]
                out.append(
                    finding(
                        text, category="quality", rule="inconsistent_terminology", title="Inconsistent terminology",
                        severity="low", confidence="high",
                        explanation=f"The same term is written as {', '.join('“' + f + '”' for f in c)}. “{preferred}” is the most frequent form in this document.",
                        note=f"Standardise on “{preferred}”.",
                        start=pos, end=pos + len(surface), replacement=match_case(orig, preferred),
                    )
                )
    return out


def analyze_quality(text: str) -> list[Finding]:
    sents = sentences(text)
    paras = paragraphs(text)
    results: list[Finding] = []
    results += filler_rule(text)
    results += vague_rule(text)
    results += superlative_rule(text, sents)
    results += guarantee_rule(text, sents)
    results += repeated_phrase_rule(text)
    results += repeated_word_rule(text, sents)
    results += repeated_idea_rule(text, sents, paras)
    results += long_sentence_rule(text, sents)
    results += acronym_rule(text)
    results += ambiguous_reference_rule(text, paras)
    results += incomplete_rule(text, paras)
    results += terminology_rule(text)
    return results
