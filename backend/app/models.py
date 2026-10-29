"""Pydantic models shared by the API, analyzers and tests."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from .config import settings

Category = Literal["factuality", "quality", "intent", "brand"]
Severity = Literal["high", "medium", "low", "info"]
Confidence = Literal["high", "medium", "low"]
Origin = Literal["rule", "ai"]
VerificationStatus = Literal["needs_verification", "supported", "not_supported", "inconclusive"]
SearchIntent = Literal["informational", "commercial", "transactional", "navigational", ""]
PageType = Literal[
    "blog_post", "how_to", "product_page", "landing_page", "comparison", "glossary", "other", ""
]
Tone = Literal["formal", "conversational", "plain", "confident", ""]


class Span(BaseModel):
    """An exact excerpt of the ORIGINAL text. `text == original[start:end]` always holds."""

    start: int
    end: int
    text: str


class Suggestion(BaseModel):
    note: str
    # When set, accepting the suggestion replaces `evidence.text` with this exact string.
    # None means the suggestion is advisory (needs a human rewrite or a source).
    replacement: Optional[str] = None


class SourceRef(BaseModel):
    url: str
    title: str = ""
    explanation: str = ""


class Verification(BaseModel):
    status: VerificationStatus = "needs_verification"
    claim_types: list[str] = Field(default_factory=list)
    suggested_source_types: list[str] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    note: str = ""


class Finding(BaseModel):
    id: str
    category: Category
    rule: str
    title: str
    severity: Severity
    confidence: Confidence
    origin: Origin = "rule"
    evidence: Optional[Span] = None
    evidence_note: str = ""
    related: list[Span] = Field(default_factory=list)
    explanation: str
    suggestion: Suggestion
    verification: Optional[Verification] = None


class InternalLink(BaseModel):
    url: str
    anchor: str

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        v = v.strip()
        if not (v.startswith("/") or v.startswith("http://") or v.startswith("https://")):
            raise ValueError("internal link URL must be a path (/...) or an http(s) URL")
        return v


class IntentBrief(BaseModel):
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    audience: str = ""
    search_intent: SearchIntent = ""
    page_type: PageType = ""
    objective: str = ""
    internal_links: list[InternalLink] = Field(default_factory=list)


class BrandBrief(BaseModel):
    guidelines: str = ""
    tone: Tone = ""
    preferred_terms: str = ""  # one rule per line: "use X instead of Y" or "Y -> X"
    avoid_terms: list[str] = Field(default_factory=list)
    example_content: str = ""
    forbid_unsupported_claims: bool = False


class AnalyzeRequest(BaseModel):
    text: str
    intent: IntentBrief = Field(default_factory=IntentBrief)
    brand: BrandBrief = Field(default_factory=BrandBrief)
    use_ai: bool = True
    verify_sources: bool = True

    @field_validator("text")
    @classmethod
    def _text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Content is empty. Paste an article or extract one from a URL.")
        if len(v) > settings.max_chars:
            raise ValueError(
                f"Content is {len(v):,} characters; the limit is {settings.max_chars:,}. "
                "Split the document and analyze it in parts."
            )
        return v


class TextStats(BaseModel):
    words: int
    characters: int
    paragraphs: int
    sentences: int


class AIStatus(BaseModel):
    enabled: bool
    provider: str
    status: Literal["ok", "disabled", "error", "skipped"]
    message: str
    checks_requiring_ai: list[str] = Field(default_factory=list)


class Summary(BaseModel):
    score: int
    score_explanation: str
    by_category: dict[str, int]
    by_severity: dict[str, int]
    by_origin: dict[str, int]
    headline: str


class AnalyzeResponse(BaseModel):
    findings: list[Finding]
    summary: Summary
    stats: TextStats
    ai: AIStatus
    verification_provider: str
    limitations: list[str]
    text_sha256: str


class ExtractRequest(BaseModel):
    url: str


class ExtractResponse(BaseModel):
    url: str
    title: str
    text: str
    characters: int
