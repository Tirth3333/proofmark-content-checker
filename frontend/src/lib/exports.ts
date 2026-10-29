import type { AnalyzeResponse, Decisions, Finding, IntentBrief, BrandBrief } from '../types'
import { CATEGORY_LABEL } from '../types'
import type { ApplyResult } from './suggestions'
import { replacementFor } from './suggestions'

export interface ReportInput {
  original: string
  result: AnalyzeResponse
  decisions: Decisions
  applied: ApplyResult
  intent: IntentBrief
  brand: BrandBrief
  generatedAt?: Date
  sourceUrl?: string
}

export function decisionLabel(f: Finding, decisions: Decisions): string {
  const d = decisions[f.id]
  if (!d) return 'pending'
  if (d.status === 'rejected') return 'rejected'
  return replacementFor(f, decisions) !== null ? 'accepted (applied)' : 'accepted (marked addressed)'
}

const csvCell = (v: unknown): string => {
  let s = String(v ?? '')
  // neutralise spreadsheet formula injection
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function findingsToCSV(findings: Finding[], decisions: Decisions): string {
  const header = [
    'id', 'category', 'severity', 'confidence', 'origin', 'rule', 'title', 'evidence', 'evidence_start', 'evidence_end',
    'evidence_note', 'explanation', 'suggestion', 'replacement', 'verification_status', 'suggested_source_types', 'sources', 'decision',
  ]
  const rows = findings.map((f) => [
    f.id, f.category, f.severity, f.confidence, f.origin === 'ai' ? 'AI assessment' : 'rule-based', f.rule, f.title,
    f.evidence?.text ?? '', f.evidence?.start ?? '', f.evidence?.end ?? '', f.evidence_note, f.explanation, f.suggestion.note,
    replacementFor(f, decisions) ?? '', f.verification?.status ?? '', f.verification?.suggested_source_types.join(' | ') ?? '',
    f.verification?.sources.map((s) => s.url).join(' | ') ?? '', decisionLabel(f, decisions),
  ])
  return [header, ...rows].map((r) => r.map(csvCell).join(',')).join('\r\n') + '\r\n'
}

const VERIFY_LABEL: Record<string, string> = {
  needs_verification: 'Needs verification',
  inconclusive: 'Sources found, not confirmed',
  supported: 'Supported by retrieved snippet',
  not_supported: 'Contradicted by retrieved snippet',
}
export const verificationLabel = (s: string) => VERIFY_LABEL[s] ?? s

function quote(s: string): string {
  return s.split('\n').map((l) => '> ' + l).join('\n')
}

export function buildMarkdownReport(r: ReportInput): string {
  const { result, decisions, applied } = r
  const when = (r.generatedAt ?? new Date()).toISOString()
  const L: string[] = []
  L.push('# Content audit report', '')
  L.push(`Generated: ${when}  `)
  if (r.sourceUrl) L.push(`Source URL: ${r.sourceUrl}  `)
  L.push(`Original text SHA-256: \`${result.text_sha256}\`  `)
  L.push(`Length: ${result.stats.words} words, ${result.stats.paragraphs} paragraphs, ${result.stats.characters} characters`, '')
  L.push('## Summary', '')
  L.push(`**Score: ${result.summary.score}/100.** ${result.summary.headline}`, '')
  L.push(`_${result.summary.score_explanation}_`, '')
  L.push('| Category | Findings |', '|---|---|')
  for (const c of ['factuality', 'quality', 'intent', 'brand'] as const) L.push(`| ${CATEGORY_LABEL[c]} | ${result.summary.by_category[c] ?? 0} |`)
  L.push('')
  L.push(`Severity: ${(['high', 'medium', 'low', 'info'] as const).map((s) => `${s} ${result.summary.by_severity[s] ?? 0}`).join(', ')}.  `)
  L.push(`Origin: rule-based ${result.summary.by_origin.rule ?? 0}, AI assessment ${result.summary.by_origin.ai ?? 0}.`, '')
  const accepted = Object.values(decisions).filter((d) => d.status === 'accepted').length
  const rejected = Object.values(decisions).filter((d) => d.status === 'rejected').length
  L.push(`Review: ${accepted} accepted, ${rejected} rejected, ${result.findings.length - accepted - rejected} pending; ${applied.edits.length} text change(s) applied to the revised version.`, '')
  L.push('## Analysis setup', '')
  L.push(`- AI review: ${result.ai.status}. ${result.ai.message}`)
  L.push(`- Source verification: ${result.verification_provider}`)
  if (r.intent.primary_keyword) L.push(`- Primary keyword: ${r.intent.primary_keyword}`)
  if (r.intent.search_intent) L.push(`- Search intent: ${r.intent.search_intent}`)
  if (r.intent.page_type) L.push(`- Page type: ${r.intent.page_type.replace('_', ' ')}`)
  if (r.intent.audience) L.push(`- Audience: ${r.intent.audience}`)
  if (r.brand.tone) L.push(`- Brand tone: ${r.brand.tone}`)
  if (result.ai.checks_requiring_ai.length) {
    L.push('', 'Checks that need the AI review (not run):')
    for (const c of result.ai.checks_requiring_ai) L.push(`- ${c}`)
  }
  L.push('')
  for (const c of ['factuality', 'quality', 'intent', 'brand'] as const) {
    const fs = result.findings.filter((f) => f.category === c)
    if (!fs.length) continue
    L.push(`## ${CATEGORY_LABEL[c]} (${fs.length})`, '')
    fs.forEach((f, i) => {
      L.push(`### ${i + 1}. ${f.title}`, '')
      L.push(`Severity **${f.severity}** · confidence ${f.confidence} · ${f.origin === 'ai' ? 'AI assessment' : 'rule-based'} · decision: ${decisionLabel(f, decisions)}`, '')
      if (f.evidence) L.push(quote(f.evidence.text), '')
      else L.push(`_${f.evidence_note}_`, '')
      L.push(f.explanation, '')
      L.push(`**Recommendation:** ${f.suggestion.note}`)
      const repl = replacementFor(f, decisions)
      if (repl !== null && f.evidence) L.push(`  Suggested change: “${f.evidence.text}” → “${repl}”`)
      if (f.verification) {
        L.push('', `**Verification:** ${verificationLabel(f.verification.status)}. ${f.verification.note}`)
        if (f.verification.suggested_source_types.length) L.push(`Suitable sources: ${f.verification.suggested_source_types.join('; ')}.`)
        for (const s of f.verification.sources) L.push(`- [${s.title || s.url}](${s.url})${s.explanation ? ': ' + s.explanation : ''}`)
      }
      L.push('')
    })
  }
  L.push('## Limitations', '')
  for (const l of result.limitations) L.push(`- ${l}`)
  L.push('')
  return L.join('\n')
}

export function download(filename: string, content: string | Blob, mime = 'text/plain;charset=utf-8') {
  const blob = typeof content === 'string' ? new Blob([content], { type: mime }) : content
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

// Anything outside printable Windows-1252 (tab and newlines allowed).
const PDF_UNSAFE = new RegExp('[^\\t\\n\\r\\u0020-\\u007E\\u00A0-\\u00FF\\u2018\\u2019\\u201C\\u201D\\u2013\\u2014\\u2026\\u20AC]', 'g')

/** jsPDF's built-in fonts only cover Windows-1252; replace anything else. */
export function pdfSafe(s: string): string {
  return s
    .replace(/[→⟶]/g, '->')
    .replace(/[·•]/g, '-')
    .replace(PDF_UNSAFE, '?')
}

export async function buildPdfReport(r: ReportInput): Promise<Blob> {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ unit: 'pt', format: 'a4' })
  const W = doc.internal.pageSize.getWidth()
  const H = doc.internal.pageSize.getHeight()
  const M = 48
  let y = M
  const write = (text: string, size = 10, style: 'normal' | 'bold' | 'italic' = 'normal', gap = 4, color: [number, number, number] = [27, 42, 58]) => {
    doc.setFont('helvetica', style)
    doc.setFontSize(size)
    doc.setTextColor(...color)
    const lines = doc.splitTextToSize(pdfSafe(text), W - 2 * M) as string[]
    for (const line of lines) {
      if (y + size > H - M) {
        doc.addPage()
        y = M
      }
      doc.text(line, M, y)
      y += size * 1.35
    }
    y += gap
  }
  // Reuse the Markdown report structure, rendered as plain styled text.
  for (const raw of buildMarkdownReport(r).split('\n')) {
    const line = raw.replace(/\*\*/g, '').replace(/`/g, '').replace(/ {2}$/, '')
    if (line.startsWith('# ')) write(line.slice(2), 18, 'bold', 8)
    else if (line.startsWith('## ')) { y += 6; write(line.slice(3), 13, 'bold', 4) }
    else if (line.startsWith('### ')) write(line.slice(4), 11, 'bold', 2)
    else if (line.startsWith('> ')) write('"' + line.slice(2) + '"', 10, 'italic', 2, [70, 80, 95])
    else if (line.startsWith('|---')) continue
    else if (line.startsWith('|')) write(line.split('|').filter(Boolean).map((c) => c.trim()).join(': '), 10)
    else if (/^_.*_$/.test(line)) write(line.slice(1, -1), 9, 'italic', 2, [90, 100, 115])
    else if (line.trim() === '') y += 4
    else write(line, 10, 'normal', 2)
  }
  return doc.output('blob')
}
