/**
 * Frontend-to-backend integration test against a REAL running backend.
 * Run with: API_URL=http://127.0.0.1:8000 npm test
 * Skipped when API_URL is not set, so the default unit run needs no server.
 */
import { applyDecisions } from '../lib/suggestions'
import { findingsToCSV } from '../lib/exports'
import { DEMO_BRAND, DEMO_INTENT, DEMO_TEXT } from '../demo'
import type { AnalyzeResponse, Decisions } from '../types'

const API = process.env.API_URL

describe.skipIf(!API)('integration with live backend', () => {
  it('health endpoint responds', async () => {
    const r = await fetch(`${API}/api/health`)
    expect(r.ok).toBe(true)
  })

  it('analyzes the demo, every evidence span matches the text, and accepted fixes apply cleanly', async () => {
    const r = await fetch(`${API}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: DEMO_TEXT, intent: DEMO_INTENT, brand: DEMO_BRAND, use_ai: true, verify_sources: true }),
    })
    expect(r.status).toBe(200)
    const data = (await r.json()) as AnalyzeResponse
    const cats = new Set(data.findings.map((f) => f.category))
    expect([...cats].sort()).toEqual(['brand', 'factuality', 'intent', 'quality'])
    for (const f of data.findings) {
      if (f.evidence) expect(DEMO_TEXT.slice(f.evidence.start, f.evidence.end)).toBe(f.evidence.text)
      if (f.category === 'factuality' && f.verification?.sources.length === 0) expect(f.verification.status).toBe('needs_verification')
    }
    const decisions: Decisions = {}
    for (const f of data.findings) if (f.suggestion.replacement !== null) decisions[f.id] = { status: 'accepted' }
    const applied = applyDecisions(DEMO_TEXT, data.findings, decisions)
    expect(applied.edits.length).toBeGreaterThan(5)
    expect(applied.text).not.toBe(DEMO_TEXT)
    expect(applied.text).toContain('customers')
    expect(findingsToCSV(data.findings, decisions).split('\r\n').length).toBe(data.findings.length + 2)
  })

  it('rejects empty content with a readable message', async () => {
    const r = await fetch(`${API}/api/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: '  ' }) })
    expect(r.status).toBe(422)
    expect((await r.json()).detail).toMatch(/empty/i)
  })
})
