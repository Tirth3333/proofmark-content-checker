import type { AnalyzeResponse, Finding } from '../types'

export const ORIGINAL = 'In order to grow, we utilize email. Our clients love it. Revenue grew 40% in 2024.'

const f = (p: Partial<Finding> & Pick<Finding, 'id' | 'category'>): Finding => ({
  rule: 'r',
  title: 'Title ' + p.id,
  severity: 'low',
  confidence: 'high',
  origin: 'rule',
  evidence: null,
  evidence_note: '',
  related: [],
  explanation: 'Because.',
  suggestion: { note: 'Do this.', replacement: null },
  verification: null,
  ...p,
})

const span = (text: string) => {
  const start = ORIGINAL.indexOf(text)
  if (start < 0) throw new Error('fixture span not found: ' + text)
  return { start, end: start + text.length, text }
}

export const FINDINGS: Finding[] = [
  f({ id: 'filler', category: 'quality', title: 'Filler language', evidence: span('In order to'), suggestion: { note: 'Shorten.', replacement: 'To' } }),
  f({ id: 'utilize', category: 'brand', title: 'Off-tone wording', evidence: span('utilize'), suggestion: { note: 'Plain word.', replacement: 'use' } }),
  // overlaps "utilize"
  f({ id: 'overlap', category: 'quality', title: 'Overlapping fix', evidence: span('we utilize email'), suggestion: { note: 'Rewrite.', replacement: 'we email' } }),
  f({ id: 'clients', category: 'brand', title: 'Use preferred terminology', severity: 'medium', evidence: span('clients'), suggestion: { note: 'Use customers.', replacement: 'customers' } }),
  f({
    id: 'claim', category: 'factuality', title: 'Needs verification: statistic', severity: 'high', evidence: span('Revenue grew 40% in 2024.'),
    suggestion: { note: 'Cite a source.', replacement: null },
    verification: { status: 'needs_verification', claim_types: ['statistic'], suggested_source_types: ['Primary report'], sources: [], note: 'Not checked.' },
  }),
  f({ id: 'section', category: 'intent', title: 'Missing section: Pricing', severity: 'medium', evidence_note: 'No passage matched “Pricing”.' }),
]

export const RESPONSE: AnalyzeResponse = {
  findings: FINDINGS,
  summary: {
    score: 62,
    score_explanation: 'Issue-density index.',
    by_category: { quality: 2, brand: 2, factuality: 1, intent: 1 },
    by_severity: { high: 1, medium: 2, low: 3 },
    by_origin: { rule: 6 },
    headline: '1 high-severity issue(s) need attention before publishing.',
  },
  stats: { words: 16, characters: ORIGINAL.length, paragraphs: 1, sentences: 3 },
  ai: { enabled: false, provider: 'none', status: 'disabled', message: 'No AI provider configured.', checks_requiring_ai: ['Weak explanations'] },
  verification_provider: 'none',
  limitations: ['Flags are not verdicts.', 'Not a ranking factor.'],
  text_sha256: 'abc',
}
