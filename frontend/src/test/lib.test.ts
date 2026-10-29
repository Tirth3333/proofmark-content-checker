import { applyDecisions, wouldConflict } from '../lib/suggestions'
import { buildSegments, textStats } from '../lib/text'
import { buildMarkdownReport, findingsToCSV, pdfSafe, buildPdfReport } from '../lib/exports'
import { emptyBrand, emptyIntent } from '../types'
import { FINDINGS, ORIGINAL, RESPONSE } from './fixtures'

describe('applyDecisions', () => {
  it('returns the original unchanged when nothing is accepted (restoration)', () => {
    const r = applyDecisions(ORIGINAL, FINDINGS, {})
    expect(r.text).toBe(ORIGINAL)
    expect(r.edits).toEqual([])
  })

  it('applies accepted replacements only to their own spans', () => {
    const r = applyDecisions(ORIGINAL, FINDINGS, { filler: { status: 'accepted' }, clients: { status: 'accepted' } })
    expect(r.text).toBe('To grow, we utilize email. Our customers love it. Revenue grew 40% in 2024.')
    expect(r.edits.map((e) => e.findingId)).toEqual(['filler', 'clients'])
    const e = r.edits[1]
    expect(r.text.slice(e.revisedStart, e.revisedEnd)).toBe('customers')
  })

  it('ignores rejected findings and advisory findings', () => {
    const r = applyDecisions(ORIGINAL, FINDINGS, { filler: { status: 'rejected' }, claim: { status: 'accepted' }, section: { status: 'accepted' } })
    expect(r.text).toBe(ORIGINAL)
  })

  it('never mutates the original string or findings', () => {
    const copy = JSON.stringify(FINDINGS)
    const original = ORIGINAL
    applyDecisions(original, FINDINGS, { filler: { status: 'accepted' }, utilize: { status: 'accepted' } })
    expect(original).toBe(ORIGINAL)
    expect(JSON.stringify(FINDINGS)).toBe(copy)
  })

  it('reports overlapping accepted edits as conflicts instead of overwriting', () => {
    const d = { utilize: { status: 'accepted' as const }, overlap: { status: 'accepted' as const } }
    const r = applyDecisions(ORIGINAL, FINDINGS, d)
    expect(r.edits).toHaveLength(1)
    expect(r.conflicts).toHaveLength(1)
    expect(r.text).toContain('email')
    expect(wouldConflict(FINDINGS[1], FINDINGS, { overlap: { status: 'accepted' } })?.id).toBe('overlap')
  })

  it('uses a user-written fix, including for advisory findings', () => {
    const r = applyDecisions(ORIGINAL, FINDINGS, { claim: { status: 'accepted', customText: 'Revenue grew 40% in 2024 (annual report).' } })
    expect(r.text.endsWith('Revenue grew 40% in 2024 (annual report).')).toBe(true)
  })

  it('skips findings whose evidence no longer matches the text', () => {
    const r = applyDecisions('Different text entirely here.', FINDINGS, { filler: { status: 'accepted' } })
    expect(r.text).toBe('Different text entirely here.')
  })
})

describe('text helpers', () => {
  it('counts words, characters and paragraphs', () => {
    expect(textStats('One two.\n\nThree four-five.')).toEqual({ words: 4, characters: 26, paragraphs: 2 })
    expect(textStats('')).toEqual({ words: 0, characters: 0, paragraphs: 0 })
  })

  it('splits overlapping highlights into segments that rebuild the text exactly', () => {
    const segs = buildSegments(ORIGINAL, FINDINGS)
    expect(segs.map((s) => s.text).join('')).toBe(ORIGINAL)
    const util = segs.find((s) => s.text === 'utilize')!
    expect(util.findingIds.sort()).toEqual(['overlap', 'utilize'])
  })
})

describe('exports', () => {
  const input = { original: ORIGINAL, result: RESPONSE, decisions: { clients: { status: 'accepted' as const } }, applied: applyDecisions(ORIGINAL, FINDINGS, { clients: { status: 'accepted' } }), intent: emptyIntent(), brand: emptyBrand(), generatedAt: new Date('2026-01-01T00:00:00Z') }

  it('builds a CSV with one row per finding, escaping and formula protection', () => {
    const evil = { ...FINDINGS[0], id: 'x', evidence: { start: 0, end: 3, text: '=HYPERLINK("a")' }, explanation: 'line1\nline2, "quoted"' }
    const csv = findingsToCSV([...FINDINGS, evil], input.decisions)
    const lines = csv.trim().split('\r\n')
    expect(lines[0].startsWith('id,category,severity')).toBe(true)
    expect(csv).toContain(`"'=HYPERLINK(""a"")"`)
    expect(csv).toContain('"line1\nline2, ""quoted"""')
    expect(csv).toContain('accepted (applied)')
    expect(csv).toContain('needs_verification')
  })

  it('builds a Markdown report with evidence, decisions and limitations', () => {
    const md = buildMarkdownReport(input)
    expect(md).toContain('# Content audit report')
    expect(md).toContain('> Revenue grew 40% in 2024.')
    expect(md).toContain('Needs verification')
    expect(md).toContain('decision: accepted (applied)')
    expect(md).toContain('## Limitations')
    expect(md).toContain('Not a ranking factor.')
    expect(md).toContain('_No passage matched “Pricing”._')
  })

  it('makes text safe for the PDF font and produces a PDF blob', async () => {
    expect(pdfSafe('a → b · c ✓')).toBe('a -> b - c ?')
    const blob = await buildPdfReport(input)
    const head = new TextDecoder().decode((await blob.arrayBuffer()).slice(0, 5))
    expect(head).toBe('%PDF-')
  })
})
