import { useEffect, useMemo, useRef, useState } from 'react'
import './styles.css'
import { analyzeContent, ApiError, getHealth, type Health } from './api'
import type { AnalyzeResponse, BrandBrief, Decision, Decisions, Finding, IntentBrief } from './types'
import { emptyBrand, emptyIntent } from './types'
import { applyDecisions, replacementFor, wouldConflict } from './lib/suggestions'
import { buildMarkdownReport, buildPdfReport, download, findingsToCSV } from './lib/exports'
import { Editor } from './components/Editor'
import { BriefPanel } from './components/BriefPanel'
import { FindingsPanel, Summary } from './components/FindingsPanel'
import { CompareView, ReviewDocument } from './components/DocumentViews'
import { ExportMenu, type ExportAction } from './components/ExportMenu'
import { DEMO_BRAND, DEMO_INTENT, DEMO_NOTE, DEMO_TEXT } from './demo'

type View = 'write' | 'review' | 'compare'
type Rail = 'findings' | 'brief'

export default function App() {
  const [text, setText] = useState('')
  const [intent, setIntent] = useState<IntentBrief>(emptyIntent)
  const [brand, setBrand] = useState<BrandBrief>(emptyBrand)
  const [useAI, setUseAI] = useState(true)
  const [health, setHealth] = useState<Health | null>(null)
  const [healthChecked, setHealthChecked] = useState(false)

  const [analyzedText, setAnalyzedText] = useState<string | null>(null)
  const [result, setResult] = useState<AnalyzeResponse | null>(null)
  const [decisions, setDecisions] = useState<Decisions>({})
  const [history, setHistory] = useState<Decisions[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [view, setView] = useState<View>('write')
  const [rail, setRail] = useState<Rail>('brief')
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const [sourceUrl, setSourceUrl] = useState<string | undefined>()
  const [isDemo, setIsDemo] = useState(false)
  const abort = useRef<AbortController | null>(null)

  useEffect(() => {
    getHealth().then((h) => {
      setHealth(h)
      setHealthChecked(true)
    })
  }, [])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3200)
    return () => clearTimeout(t)
  }, [toast])

  const maxChars = health?.limits.max_chars ?? 100_000
  const stale = result !== null && analyzedText !== text
  const applied = useMemo(
    () => (result && analyzedText !== null ? applyDecisions(analyzedText, result.findings, decisions) : { text: '', edits: [], conflicts: [] }),
    [result, analyzedText, decisions],
  )
  const conflictIds = useMemo(() => new Set(applied.conflicts.map((c) => c.findingId)), [applied])

  async function analyze() {
    if (!text.trim()) {
      setError('Content is empty. Paste an article or extract one from a URL.')
      return
    }
    abort.current?.abort()
    const ctl = new AbortController()
    abort.current = ctl
    setAnalyzing(true)
    setError(null)
    try {
      const r = await analyzeContent({ text, intent, brand, use_ai: useAI, verify_sources: true }, ctl.signal)
      setResult(r)
      setAnalyzedText(text)
      setDecisions({})
      setHistory([])
      setSelectedId(null)
      setView('review')
      setRail('findings')
      setToast(`Analysis complete: ${r.findings.length} findings.`)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError(e instanceof ApiError ? e.message : 'Analysis failed unexpectedly.')
    } finally {
      setAnalyzing(false)
    }
  }

  function decide(next: Decisions) {
    setHistory((h) => [...h.slice(-49), decisions])
    setDecisions(next)
  }
  function accept(f: Finding, customText?: string) {
    const d: Decision = { status: 'accepted', ...(customText !== undefined ? { customText } : {}) }
    const nextDecisions = { ...decisions, [f.id]: d }
    const clash = wouldConflict(f, result!.findings, decisions)
    decide(nextDecisions)
    if (clash && replacementFor(f, nextDecisions) !== null) setToast('Accepted, but not applied: it overlaps an earlier accepted change.')
  }
  function reject(f: Finding) {
    decide({ ...decisions, [f.id]: { status: 'rejected' } })
  }
  function clearDecision(f: Finding) {
    const n = { ...decisions }
    delete n[f.id]
    decide(n)
  }
  function undo() {
    if (!history.length) return
    setDecisions(history[history.length - 1])
    setHistory((h) => h.slice(0, -1))
  }
  function restoreOriginal() {
    if (!Object.keys(decisions).length) return
    decide({})
    setToast('All decisions cleared. The revised text matches the original again.')
  }
  function acceptAllRule(fixOnly: boolean) {
    if (!result) return
    const n = { ...decisions }
    for (const f of result.findings) {
      if (n[f.id] || f.origin !== 'rule' || !f.evidence) continue
      if (fixOnly && f.suggestion.replacement === null) continue
      n[f.id] = { status: 'accepted' }
    }
    decide(n)
  }

  function loadDemo() {
    setText(DEMO_TEXT)
    setIntent(DEMO_INTENT)
    setBrand(DEMO_BRAND)
    setIsDemo(true)
    setSourceUrl(undefined)
    setView('write')
    setToast('Demo article and brief loaded. Press Analyze.')
  }

  const fileBase = (sourceUrl ? new URL(sourceUrl).hostname.replace(/\W+/g, '-') : isDemo ? 'demo-article' : 'content') + '-audit'
  const reportInput = () => ({ original: analyzedText!, result: result!, decisions, applied, intent, brand, sourceUrl })
  const exportActions: ExportAction[] = [
    { id: 'md', label: 'Audit report (.md)', detail: 'Summary, evidence, recommendations, limitations', run: () => download(`${fileBase}.md`, buildMarkdownReport(reportInput()), 'text/markdown;charset=utf-8') },
    { id: 'pdf', label: 'Audit report (.pdf)', detail: 'Same report as a printable PDF', run: async () => download(`${fileBase}.pdf`, await buildPdfReport(reportInput())) },
    { id: 'csv', label: 'Findings (.csv)', detail: 'One row per finding, with decisions', run: () => download(`${fileBase}-findings.csv`, findingsToCSV(result!.findings, decisions), 'text/csv;charset=utf-8') },
    { id: 'rev-md', label: 'Revised content (.md)', detail: `${applied.edits.length} accepted change(s) applied`, run: () => download(`${fileBase}-revised.md`, applied.text, 'text/markdown;charset=utf-8') },
    { id: 'rev-txt', label: 'Revised content (.txt)', detail: 'Plain text', run: () => download(`${fileBase}-revised.txt`, applied.text) },
    { id: 'orig', label: 'Original content (.txt)', detail: 'Exactly as analyzed', run: () => download(`${fileBase}-original.txt`, analyzedText ?? '') },
  ]

  const pending = result ? result.findings.length - Object.keys(decisions).length : 0

  return (
    <div className="app">
      <header className="appbar">
        <div className="brand">
          <svg width="26" height="26" viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" rx="7" fill="#1B2A3A" /><path d="M8 22h16" stroke="#E5484D" strokeWidth="2.5" strokeLinecap="round" /><path d="M9 17c2-3 4 3 6 0s4 3 6 0" stroke="#7FA7F5" strokeWidth="2" fill="none" strokeLinecap="round" /><path d="M11 11h10" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" /></svg>
          <div>
            <h1>Proofmark</h1>
            <p>Content quality and factuality review</p>
          </div>
        </div>
        <div className="appbar-right">
          <span className={`pill ${health?.ai.enabled ? 'pill-on' : 'pill-off'}`} title={health?.ai.message}>
            {!healthChecked ? 'Connecting…' : health === null ? 'Server offline' : health.ai.enabled ? `AI review: ${health.ai.provider}` : 'Rule-based mode'}
          </span>
          <ExportMenu actions={exportActions} disabled={!result} />
        </div>
      </header>

      {healthChecked && health === null && (
        <p className="banner banner-error" role="alert">The analysis server isn't reachable. Start the backend (see README) and reload.</p>
      )}

      <main className="workspace">
        <section className="doc-col" aria-label="Document">
          <div className="doc-toolbar">
            <div className="tabs" role="tablist" aria-label="Document view">
              <button role="tab" aria-selected={view === 'write'} onClick={() => setView('write')}>Write</button>
              <button role="tab" aria-selected={view === 'review'} onClick={() => setView('review')} disabled={!result}>Review</button>
              <button role="tab" aria-selected={view === 'compare'} onClick={() => setView('compare')} disabled={!result}>
                Compare{applied.edits.length ? ` (${applied.edits.length})` : ''}
              </button>
            </div>
            {result && view !== 'write' && (
              <div className="review-tools">
                <button className="btn btn-quiet btn-sm" onClick={undo} disabled={!history.length}>Undo</button>
                <button className="btn btn-quiet btn-sm" onClick={restoreOriginal} disabled={!Object.keys(decisions).length}>Restore original</button>
                <button className="btn btn-quiet btn-sm" onClick={() => acceptAllRule(true)} title="Accept every pending rule-based finding that has a concrete replacement">
                  Accept all simple fixes
                </button>
              </div>
            )}
          </div>

          {isDemo && (
            <p className="banner banner-demo"><strong>Demonstration content.</strong> {DEMO_NOTE.replace(/^DEMONSTRATION CONTENT\.\s*/, '')}</p>
          )}
          {stale && view !== 'write' && (
            <p className="banner banner-warn" role="status">
              The editor text has changed since this analysis. Highlights refer to the analyzed version.{' '}
              <button className="link" onClick={analyze}>Re-analyze</button>
            </p>
          )}
          {error && <p className="banner banner-error" role="alert">{error}</p>}

          <div className="page">
            {view === 'write' && (
              <Editor
                text={text}
                onChange={(t) => setText(t)}
                maxChars={maxChars}
                analyzing={analyzing}
                canReset={analyzedText !== null && analyzedText !== text}
                stale={stale}
                onAnalyze={analyze}
                onClear={() => { setText(''); setError(null) }}
                onReset={() => analyzedText !== null && setText(analyzedText)}
                onLoadDemo={loadDemo}
                onExtracted={(t, url) => { setText(t); setSourceUrl(url); setIsDemo(false) }}
              />
            )}
            {view === 'review' && result && analyzedText !== null && (
              <ReviewDocument text={analyzedText} findings={result.findings} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setRail('findings') }} />
            )}
            {view === 'compare' && result && analyzedText !== null && (
              <CompareView
                original={analyzedText}
                applied={applied}
                onCopy={async () => {
                  try {
                    await navigator.clipboard.writeText(applied.text)
                    setToast('Revised text copied.')
                  } catch {
                    setToast('Copy failed. Use Export → Revised content instead.')
                  }
                }}
              />
            )}
            {analyzing && (
              <div className="loading" role="status" aria-live="polite">
                <span className="spinner" aria-hidden="true" /> Checking claims, wording, intent and voice…
              </div>
            )}
          </div>
        </section>

        <aside className="rail" aria-label="Review panel">
          <div className="seg rail-tabs" role="tablist" aria-label="Panel">
            <button role="tab" aria-selected={rail === 'findings'} onClick={() => setRail('findings')}>
              Findings{result ? ` (${pending} pending)` : ''}
            </button>
            <button role="tab" aria-selected={rail === 'brief'} onClick={() => setRail('brief')}>Brief</button>
          </div>
          {rail === 'brief' && (
            <BriefPanel intent={intent} brand={brand} onIntent={setIntent} onBrand={setBrand} useAI={useAI} onUseAI={setUseAI} aiAvailable={!!health?.ai.enabled} />
          )}
          {rail === 'findings' && !result && (
            <div className="empty-state">
              <h2>No review yet</h2>
              <p>Paste content or extract it from a URL, optionally fill in the brief, then press Analyze. Every finding links back to the exact text it refers to.</p>
              <button className="btn" onClick={loadDemo}>Try the demo article</button>
            </div>
          )}
          {rail === 'findings' && result && (
            <>
              <Summary result={result} />
              <FindingsPanel
                result={result}
                decisions={decisions}
                selectedId={selectedId}
                conflicts={conflictIds}
                onSelect={(id) => { setSelectedId(id === selectedId ? null : id); if (view === 'write') setView('review') }}
                onAccept={accept}
                onReject={reject}
                onClear={clearDecision}
              />
              <details className="limits">
                <summary>Limitations of this review</summary>
                <ul>{result.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              </details>
            </>
          )}
        </aside>
      </main>
      <div className="toast" role="status" aria-live="polite">{toast}</div>
    </div>
  )
}
