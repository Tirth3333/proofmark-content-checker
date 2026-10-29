"""Search-intent and completeness heuristics.

These are editorial heuristics derived from the brief the user supplies. They are not
search-engine ranking factors and cannot predict or guarantee rankings.
"""
from __future__ import annotations

import re

from ..models import Finding, IntentBrief
from .common import finding
from .text_utils import Segment, is_heading, paragraphs, sentences, stem, words

# expected sections per page type / intent: (label, detection regex, why it matters)
SECTION_RULES: dict[str, list[tuple[str, str, str]]] = {
    "how_to": [
        ("Step-by-step instructions", r"(?im)^\s*(?:\d+[.)]|step\s+\d+|#+\s*step)|\bstep\s+(?:one|1)\b|\bfirst,", "How-to readers expect ordered steps they can follow."),
        ("Prerequisites or what you need", r"\b(?:prerequisite|you(?:'ll| will) need|before you (?:start|begin)|requirements?|what you need)\b", "Readers need to know what to prepare before starting."),
        ("Troubleshooting or common mistakes", r"\b(?:troubleshoot|common (?:mistakes|problems|issues|errors)|if (?:it|this) (?:doesn't|does not) work|pitfalls)\b", "Covers the questions readers have when a step fails."),
    ],
    "comparison": [
        ("Side-by-side comparison criteria", r"\b(?:vs\.?|versus|compared (?:to|with)|comparison)\b", "Comparison searches expect explicit criteria."),
        ("Pros and cons", r"\b(?:pros|cons|advantages|disadvantages|drawbacks|downsides)\b", "Readers weighing options look for trade-offs."),
        ("Pricing", r"\b(?:price|pricing|cost|per month|/mo|free plan|plans?)\b", "Cost is usually a deciding factor."),
        ("Recommendation or verdict", r"\b(?:verdict|our pick|we recommend|best for|bottom line|which (?:one|should))\b", "Comparison readers want a clear recommendation."),
    ],
    "product_page": [
        ("Specifications or features", r"\b(?:features?|specifications?|specs|includes|what's included)\b", "Buyers check what they actually get."),
        ("Pricing", r"\b(?:price|pricing|cost|\$|₹|€|£|per month|buy)\b", "Transactional visitors need the price."),
        ("Call to action", r"\b(?:buy now|add to cart|get started|sign up|start (?:your )?(?:free )?trial|contact (?:us|sales)|book a demo|order)\b", "The page needs a clear next step."),
        ("Shipping, returns or support terms", r"\b(?:shipping|delivery|returns?|refund|warranty|support)\b", "Reduces purchase hesitation."),
    ],
    "landing_page": [
        ("Clear value proposition near the top", r"", "Visitors decide quickly whether the page is relevant."),
        ("Call to action", r"\b(?:get started|sign up|start (?:your )?(?:free )?trial|contact (?:us|sales)|book a demo|request a (?:quote|demo)|download|subscribe|join)\b", "The page needs a clear next step."),
        ("Social proof or evidence", r"\b(?:customers?|testimonial|case stud(?:y|ies)|review|rated|trusted by)\b", "Supports claims with evidence."),
    ],
    "glossary": [
        ("Definition", r"\b(?:is a|is an|refers to|is the|means|defined as)\b", "Definition searches expect a direct answer."),
        ("Example", r"\b(?:for example|for instance|e\.g\.|such as|example)\b", "Examples make definitions concrete."),
    ],
    "blog_post": [
        ("Conclusion or key takeaways", r"\b(?:conclusion|in summary|to sum up|key takeaways?|final thoughts|bottom line|next steps)\b", "Helps readers retain the main points."),
    ],
}
INTENT_RULES: dict[str, list[tuple[str, str, str]]] = {
    "informational": [
        ("Direct definition or answer", r"\b(?:is a|is an|refers to|means|defined as|is the process)\b", "Informational searchers want the answer early."),
        ("Examples", r"\b(?:for example|for instance|such as|e\.g\.|example)\b", "Examples help readers apply the information."),
    ],
    "commercial": [
        ("Comparison or alternatives", r"\b(?:vs\.?|versus|alternatives?|compared|comparison)\b", "Commercial-investigation readers compare options."),
        ("Pricing", r"\b(?:price|pricing|cost|per month|free plan|plans?)\b", "Cost is a key evaluation question."),
        ("Who it's for", r"\b(?:best for|ideal for|who (?:it|this) is for|suited (?:to|for)|if you are)\b", "Helps readers self-qualify."),
    ],
    "transactional": [
        ("Call to action", r"\b(?:buy|order|get started|sign up|start (?:your )?(?:free )?trial|book|subscribe|download|add to cart)\b", "Transactional visitors need an obvious next step."),
        ("Pricing", r"\b(?:price|pricing|cost|\$|₹|€|£|per month|free)\b", "Price is expected on transactional pages."),
    ],
    "navigational": [
        ("Brand or destination named early", r"", "Navigational visitors want to confirm they reached the right place."),
    ],
}

QUESTION_TEMPLATES = [
    ("What is {kw}?", r"\b(?:is a|is an|refers to|means|defined as|is the)\b", "definition"),
    ("How does {kw} work?", r"\b(?:works? by|how (?:it|they|this) works?|process|step|mechanism)\b", "how it works"),
    ("Why does {kw} matter?", r"\b(?:because|benefits?|why|helps?|so that|important)\b", "benefits"),
    ("How much does {kw} cost?", r"\b(?:price|pricing|cost|free|\$|₹|€|£|per month|budget)\b", "cost"),
    ("How do I get started with {kw}?", r"\b(?:get started|start by|first step|step 1|begin by|how to start)\b", "getting started"),
]


def _kw_regex(kw: str) -> re.Pattern[str]:
    parts = [re.escape(stem(p)) + r"\w*" for p in kw.split()]
    return re.compile(r"\b" + r"[\s\-]+".join(parts) + r"\b", re.I)


def _evidence_intro(text: str, paras: list[Segment]) -> Segment | None:
    for p in paras:
        if not is_heading(p):
            return p
    return paras[0] if paras else None


def analyze_intent(text: str, brief: IntentBrief) -> list[Finding]:
    out: list[Finding] = []
    has_brief = any([brief.primary_keyword, brief.secondary_keywords, brief.search_intent, brief.page_type, brief.audience, brief.objective, brief.internal_links])
    if not has_brief:
        return out
    paras = paragraphs(text)
    sents = sentences(text)
    intro = _evidence_intro(text, paras)
    total_words = len(words(text))
    kw = brief.primary_keyword.strip()

    # ---- primary keyword coverage
    if kw:
        kre = _kw_regex(kw)
        hits = list(kre.finditer(text))
        if not hits:
            out.append(
                finding(
                    text, category="intent", rule="keyword_missing", title="Primary keyword topic not addressed",
                    severity="high", confidence="high",
                    explanation=f"The primary keyword “{kw}” (or a close inflection) does not appear anywhere. The draft may not clearly address the topic you are targeting.",
                    note=f"State the topic “{kw}” explicitly in the title and introduction, in natural language.",
                    start=intro.start if intro else None, end=intro.end if intro else None,
                    evidence_note="" if intro else "No text matched the primary keyword.",
                )
            )
        elif intro and not any(intro.start <= h.start() < intro.end for h in hits):
            first_150 = text[: min(len(text), 900)]
            if not kre.search(first_150):
                out.append(
                    finding(
                        text, category="intent", rule="keyword_not_in_intro", title="Introduction doesn't name the topic",
                        severity="medium", confidence="high",
                        explanation=f"“{kw}” first appears {hits[0].start()} characters into the text, not in the introduction. Readers scanning the opening may not see that the page answers their query.",
                        note=f"Mention “{kw}” in the first one or two sentences.",
                        start=intro.start, end=intro.end,
                    )
                )
        heading_segs = [p for p in paras if is_heading(p)]
        if heading_segs and not any(kre.search(h.text) for h in heading_segs):
            out.append(
                finding(
                    text, category="intent", rule="keyword_not_in_headings", title="No heading mentions the topic",
                    severity="low", confidence="medium",
                    explanation=f"None of the {len(heading_segs)} headings mention “{kw}”. Headings help readers confirm they're on the right page.",
                    note="Work the topic into the main heading or a key sub-heading where it reads naturally.",
                    start=heading_segs[0].start, end=heading_segs[0].end,
                )
            )

    for sk in [s.strip() for s in brief.secondary_keywords if s.strip()]:
        if not _kw_regex(sk).search(text):
            out.append(
                finding(
                    text, category="intent", rule="secondary_keyword_missing", title=f"Subtopic not covered: {sk}",
                    severity="low", confidence="high",
                    explanation=f"The secondary keyword “{sk}” from your brief does not appear. If it reflects something your audience asks about, the draft doesn't cover it yet.",
                    note=f"Add a short section or paragraph addressing “{sk}” if it's relevant to readers.",
                    evidence_note=f"No text matched “{sk}”.",
                )
            )

    # ---- introduction clarity
    if intro:
        iw = len(words(intro.text))
        if iw > 120:
            out.append(
                finding(
                    text, category="intent", rule="long_intro", title="Introduction takes too long to get to the point",
                    severity="medium", confidence="medium",
                    explanation=f"The opening paragraph is {iw} words. Readers who arrive from search usually want the answer or a clear promise within the first few sentences.",
                    note="Lead with a one- or two-sentence answer or summary, then expand.",
                    start=intro.start, end=intro.end,
                )
            )
        if re.match(r"(?i)\s*(?:in today'?s|in this (?:day and age|fast)|have you ever wondered|since the dawn|we all know|imagine)", intro.text):
            out.append(
                finding(
                    text, category="intent", rule="generic_intro", title="Generic opening line",
                    severity="low", confidence="medium",
                    explanation="The introduction opens with a stock phrase rather than the topic or the reader's question.",
                    note="Open with the specific question the reader has, or the direct answer.",
                    start=next((x.start for x in sents if x.start >= intro.start), intro.start),
                    end=next((x.end for x in sents if x.start >= intro.start), intro.end),
                )
            )

    # ---- expected sections
    rules = list(SECTION_RULES.get(brief.page_type, [])) + list(INTENT_RULES.get(brief.search_intent, []))
    seen_labels = set()
    for label, pattern, why in rules:
        if label in seen_labels:
            continue
        seen_labels.add(label)
        if not pattern:
            # top-of-page checks
            top = text[:600]
            if label.startswith("Clear value") and kw and _kw_regex(kw).search(top):
                continue
            if label.startswith("Brand or destination") and kw and _kw_regex(kw).search(text[:300]):
                continue
            if not kw:
                continue
        elif re.search(pattern, text):
            continue
        out.append(
            finding(
                text, category="intent", rule="missing_section", title=f"Missing section: {label}",
                severity="medium", confidence="medium",
                explanation=f"For a {_pretty(brief.page_type or brief.search_intent)} page, readers usually expect this. {why} No text in the draft matched this section's typical wording.",
                note=f"Consider adding a “{label}” section.",
                evidence_note=f"No passage matched the expected “{label}” content.",
            )
        )

    # ---- likely questions (FAQ opportunities)
    if kw:
        kre = _kw_regex(kw)
        cues = [s for s in sents if kre.search(s.text)]
        cue_text = " ".join(s.text for s in sents)
        unanswered = []
        for q, cue, label in QUESTION_TEMPLATES:
            if label == "cost" and brief.search_intent == "informational" and brief.page_type in ("glossary", "how_to"):
                continue
            pool = " ".join(s.text for s in cues) if label in ("definition",) else cue_text
            if not re.search(cue, pool, re.I):
                unanswered.append(q.format(kw=kw))
        aud = f" for {brief.audience.strip()}" if brief.audience.strip() else ""
        for q in unanswered:
            out.append(
                finding(
                    text, category="intent", rule="unanswered_question", title=f"Likely question not answered: {q}",
                    severity="low", confidence="low",
                    explanation=f"This is a common question{aud} about a topic like “{kw}”. The draft has no passage that appears to answer it (keyword/cue-word heuristic; an AI review can judge this more accurately).",
                    note=f"Answer it in the body, or add it to an FAQ section: “{q}”.",
                    evidence_note="No passage matched the answer cues for this question.",
                )
            )
        if unanswered and not re.search(r"(?i)\b(?:FAQ|frequently asked|questions)\b", text):
            out.append(
                finding(
                    text, category="intent", rule="faq_opportunity", title="FAQ section opportunity",
                    severity="info", confidence="low",
                    explanation=f"{len(unanswered)} common question(s) aren't answered and the draft has no FAQ section.",
                    note="Add a short FAQ answering: " + "; ".join(unanswered[:4]),
                    evidence_note="No FAQ section found.",
                )
            )

    # ---- thin content for page type
    minimum = {"how_to": 400, "comparison": 600, "blog_post": 500, "glossary": 150, "product_page": 150, "landing_page": 150}.get(brief.page_type, 0)
    if minimum and total_words < minimum:
        out.append(
            finding(
                text, category="intent", rule="thin_content", title="Draft may be too short to cover the topic",
                severity="low", confidence="low",
                explanation=f"The draft has {total_words} words. {_pretty(brief.page_type).capitalize()} pages that fully answer a query usually need more depth (rule of thumb: {minimum}+ words). Length alone isn't a quality signal; check the missing-section findings.",
                note="Expand the sections readers need rather than padding.",
                evidence_note=f"Document length: {total_words} words.",
            )
        )

    # ---- objective / CTA
    obj = brief.objective.lower()
    if obj and re.search(r"sign ?up|convert|demo|trial|lead|purchase|buy|subscribe|download|contact", obj):
        if not re.search(r"(?i)\b(?:sign up|get started|start (?:a |your )?(?:free )?trial|book a demo|request a demo|contact us|subscribe|download|buy|order now|try it|learn more)\b", text):
            out.append(
                finding(
                    text, category="intent", rule="missing_cta", title="No call to action for the stated objective",
                    severity="medium", confidence="medium",
                    explanation=f"Your objective is “{brief.objective.strip()}”, but the draft contains no call to action that supports it.",
                    note="Add a clear, specific next step near the conclusion (and optionally after the introduction).",
                    evidence_note="No call-to-action wording found.",
                )
            )

    # ---- internal links (only URLs the user supplied)
    for link in brief.internal_links:
        anchor = link.anchor.strip()
        if not anchor:
            continue
        if link.url in text:
            continue
        m = re.search(r"(?<![\[\w])" + re.escape(anchor) + r"(?![\w\]])", text, re.I)
        if m:
            out.append(
                finding(
                    text, category="intent", rule="internal_link", title="Internal link opportunity",
                    severity="info", confidence="high",
                    explanation=f"“{m.group(0)}” matches the anchor text you supplied for {link.url}, and that page isn't linked yet.",
                    note=f"Link this phrase to {link.url}.",
                    start=m.start(), end=m.end(), replacement=f"[{m.group(0)}]({link.url})",
                )
            )
    return out


def _pretty(v: str) -> str:
    return v.replace("_", "-").replace("how-to", "how-to") if v else "this"
