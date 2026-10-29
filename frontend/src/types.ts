export type Category = 'factuality' | 'quality' | 'intent' | 'brand'
export type Severity = 'high' | 'medium' | 'low' | 'info'
export type Confidence = 'high' | 'medium' | 'low'
export type Origin = 'rule' | 'ai'

export interface Span {
  start: number
  end: number
  text: string
}

export interface SourceRef {
  url: string
  title: string
  explanation: string
}

export interface Verification {
  status: 'needs_verification' | 'supported' | 'not_supported' | 'inconclusive'
  claim_types: string[]
  suggested_source_types: string[]
  sources: SourceRef[]
  note: string
}

export interface Finding {
  id: string
  category: Category
  rule: string
  title: string
  severity: Severity
  confidence: Confidence
  origin: Origin
  evidence: Span | null
  evidence_note: string
  related: Span[]
  explanation: string
  suggestion: { note: string; replacement: string | null }
  verification: Verification | null
}

export interface AnalyzeResponse {
  findings: Finding[]
  summary: {
    score: number
    score_explanation: string
    by_category: Partial<Record<Category, number>>
    by_severity: Partial<Record<Severity, number>>
    by_origin: Partial<Record<Origin, number>>
    headline: string
  }
  stats: { words: number; characters: number; paragraphs: number; sentences: number }
  ai: {
    enabled: boolean
    provider: string
    status: 'ok' | 'disabled' | 'error' | 'skipped'
    message: string
    checks_requiring_ai: string[]
  }
  verification_provider: string
  limitations: string[]
  text_sha256: string
}

export interface InternalLink {
  url: string
  anchor: string
}

export interface IntentBrief {
  primary_keyword: string
  secondary_keywords: string[]
  audience: string
  search_intent: '' | 'informational' | 'commercial' | 'transactional' | 'navigational'
  page_type: '' | 'blog_post' | 'how_to' | 'product_page' | 'landing_page' | 'comparison' | 'glossary' | 'other'
  objective: string
  internal_links: InternalLink[]
}

export interface BrandBrief {
  guidelines: string
  tone: '' | 'formal' | 'conversational' | 'plain' | 'confident'
  preferred_terms: string
  avoid_terms: string[]
  example_content: string
  forbid_unsupported_claims: boolean
}

export type DecisionStatus = 'accepted' | 'rejected'
export interface Decision {
  status: DecisionStatus
  /** user-written replacement for advisory findings (or an edited suggestion) */
  customText?: string
}
export type Decisions = Record<string, Decision>

export const CATEGORY_LABEL: Record<Category, string> = {
  factuality: 'Factuality',
  quality: 'Writing quality',
  intent: 'Search intent',
  brand: 'Brand voice',
}

export const SEVERITY_RANK: Record<Severity, number> = { high: 0, medium: 1, low: 2, info: 3 }

export const emptyIntent = (): IntentBrief => ({
  primary_keyword: '',
  secondary_keywords: [],
  audience: '',
  search_intent: '',
  page_type: '',
  objective: '',
  internal_links: [],
})

export const emptyBrand = (): BrandBrief => ({
  guidelines: '',
  tone: '',
  preferred_terms: '',
  avoid_terms: [],
  example_content: '',
  forbid_unsupported_claims: false,
})
