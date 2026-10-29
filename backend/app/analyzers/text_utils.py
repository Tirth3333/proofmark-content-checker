"""Offset-preserving text segmentation helpers.

Every span produced here indexes into the ORIGINAL string, so evidence shown to the
user is always an exact excerpt (original[start:end]).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..models import Span

WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")
_PARA_SPLIT = re.compile(r"\n\s*\n")
# Sentence end: . ! ? followed by whitespace + (capital/quote/digit) or end; avoid common abbreviations.
_ABBREV = {"e.g", "i.e", "etc", "vs", "mr", "mrs", "ms", "dr", "inc", "ltd", "co", "st", "no", "fig", "approx", "u.s"}

STOPWORDS = set(
    """a an the and or but if then else when while of to in on at by for with about against between into
    through during before after above below from up down out off over under again further once here there
    all any both each few more most other some such no nor not only own same so than too very can will just
    should now is are was were be been being have has had having do does did doing i me my we our ours you
    your yours he him his she her it its they them their what which who whom this that these those am
    would could also may might must shall it's don't isn't aren't wasn't weren't won't can't you're we're
    they're there's that's how why where one get got make makes made like""".split()
)


@dataclass(frozen=True)
class Segment:
    start: int
    end: int
    text: str

    def span(self) -> Span:
        return Span(start=self.start, end=self.end, text=self.text)


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(*parts: object) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def paragraphs(text: str) -> list[Segment]:
    out: list[Segment] = []
    pos = 0
    for m in list(_PARA_SPLIT.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        chunk = text[pos:end]
        stripped = chunk.strip()
        if stripped:
            s = pos + (len(chunk) - len(chunk.lstrip()))
            out.append(Segment(s, s + len(stripped), stripped))
        if m:
            pos = m.end()
    return out


def _is_abbrev(text: str, dot_idx: int) -> bool:
    j = dot_idx
    while j > 0 and (text[j - 1].isalpha() or text[j - 1] == "."):
        j -= 1
    token = text[j:dot_idx].lower()
    if token in _ABBREV:
        return True
    # single initials like "J." or decimals like "3.5"
    if len(token) == 1 and token.isalpha():
        return True
    return False


def sentences(text: str) -> list[Segment]:
    """Split into sentences, also treating single newlines (headings, list items) as boundaries."""
    out: list[Segment] = []
    for line_m in re.finditer(r"[^\n]+", text):
        line = line_m.group(0)
        base = line_m.start()
        start = 0
        i = 0
        while i < len(line):
            ch = line[i]
            if ch in ".!?":
                # extend over closing quotes/brackets and repeated punctuation
                k = i + 1
                while k < len(line) and line[k] in "\"'”’)]!?.":
                    k += 1
                at_end = k >= len(line)
                next_ok = at_end or (line[k].isspace() and (k + 1 >= len(line) or not line[k + 1].islower()))
                if ch == "." and i + 1 < len(line) and line[i + 1].isdigit():
                    next_ok = False
                if next_ok and not (ch == "." and _is_abbrev(line, i)):
                    _push(out, line, base, start, k)
                    start = k
                    i = k
                    continue
            i += 1
        _push(out, line, base, start, len(line))
    return out


def _push(out: list[Segment], line: str, base: int, a: int, b: int) -> None:
    chunk = line[a:b]
    stripped = chunk.strip()
    if not stripped:
        return
    s = a + (len(chunk) - len(chunk.lstrip()))
    out.append(Segment(base + s, base + s + len(stripped), stripped))


def words(text: str) -> list[Segment]:
    return [Segment(m.start(), m.end(), m.group(0)) for m in WORD_RE.finditer(text)]


def stats(text: str) -> dict[str, int]:
    return {
        "words": len(WORD_RE.findall(text)),
        "characters": len(text),
        "paragraphs": len(paragraphs(text)),
        "sentences": len(sentences(text)),
    }


def norm(word: str) -> str:
    w = word.lower().replace("’", "'")
    for suf in ("'s",):
        if w.endswith(suf):
            w = w[: -len(suf)]
    return w


def stem(word: str) -> str:
    """Very light suffix stripper (enough for lexical-overlap comparisons)."""
    w = norm(word)
    for suf in ("ingly", "edly", "ing", "ed", "es", "ly", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def content_stems(text: str) -> list[str]:
    return [stem(w.text) for w in words(text) if norm(w.text) not in STOPWORDS and len(w.text) > 2]


def is_heading(seg: Segment) -> bool:
    t = seg.text
    if t.startswith("#"):
        return True
    if re.search(r"\b(?:and|then|the|to|of|a|an|with|or|but|for|that|because|so)\s*$", t, re.I):
        return False
    return len(t) < 80 and "\n" not in t and not t.rstrip().endswith((".", "!", "?", ":", ",", ";")) and len(t.split()) <= 10


def find_all(pattern: re.Pattern[str], text: str) -> list[re.Match[str]]:
    return list(pattern.finditer(text))


def sentence_at(sents: list[Segment], pos: int) -> Segment | None:
    for s in sents:
        if s.start <= pos < s.end:
            return s
    return None


def is_sentence_start(text: str, pos: int) -> bool:
    j = pos - 1
    while j >= 0 and text[j] in " \t\"'“‘(":
        j -= 1
    return j < 0 or text[j] in ".!?\n#:*-"


def removal_edit(text: str, start: int, end: int) -> tuple[int, int, str]:
    """Return (start, end, replacement) that deletes text[start:end] cleanly.

    Consumes one adjacent space and, when the deletion is at a sentence start,
    re-capitalises the following word so the edit stays grammatical.
    """
    s, e = start, end
    if e < len(text) and text[e] in ",;" and (e + 1 >= len(text) or text[e + 1] == " "):
        e += 1  # "In today's world, choosing" -> "Choosing"
    if e < len(text) and text[e] == " ":
        e += 1
    elif s > 0 and text[s - 1] == " ":
        s -= 1
    if is_sentence_start(text, start):
        m = re.match(r"[A-Za-z][\w'’\-]*", text[e:])
        if m:
            nxt = m.group(0)
            return start, e + len(nxt), nxt[0].upper() + nxt[1:]
    return s, e, ""


def match_case(original: str, replacement: str) -> str:
    if not replacement:
        return replacement
    if original.isupper() and len(original) > 1:
        return replacement.upper()
    if original[:1].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement
