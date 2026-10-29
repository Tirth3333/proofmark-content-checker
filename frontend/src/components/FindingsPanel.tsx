import { useMemo, useState } from 'react'
import type { AnalyzeResponse, Category, Decisions, Finding, Severity } from '../types'
import { CATEGORY_LABEL, SEVERITY_RANK } from '../types'
import { FindingCard } from './FindingCard'
import { wouldConflict } from '../lib/suggestions'

interface Props {
  result: AnalyzeResponse
  decisions: Decisions
  selectedId: string | null
  conflicts: Set<string>
  onSelect: (id: string) => void
  onAccept: (f: Finding, customText?: string) => void
  onReject: (f: Finding) => void
  onClear: (f: Finding) => void
}

const CATS: Category[] = ['factuality', 'quality', 'intent', 'brand']
const SEVS: Severity[] = ['high', 'medium', 'low', 'info']
type Sort = 'position' | 'severity' | 'category'
type Status = 'all' | 'pending' | 'accepted' | 'rejected'

export function Summary({ result }: { result: AnalyzeResponse }) {
  const { summary, ai } = result
  const total = result.findings.length || 1
  return (
    <section className="summary" aria-label="Audit summary">
      <div className="score-row">
        <p className="score" title={summary.score_explanation}>
          <span className="score-n">{summary.score}</span>
          <span className="score-d">/100</span>
        </p>
        <div>
          <p className="headline">{summary.headline}</p>
          <details className="explain">
            <summary>How the score works</summary>
            <p>{summary.score_explanation}</p>
          </details>
        </div>
      </div>
      <div className="cat-bars" role="list">
        {CATS.map((c) => {
          const n = summary.by_category[c] ?? 0
          return (
            <div key={c} className={`cat-bar cat-${c}`} role="listitem">
              <span className="cat-name">{CATEGORY_LABEL[c]}</span>
              <span className="bar"><span style={{ width: `${(n / total) * 100}%` }} /></span>
              <span className="cat-n">{n}</span>
            </div>
          )
        })}
      </div>
      <p className="sev-line">
        {SEVS.map((s) => (
          <span key={s} className={`sev sev-${s}`}>{summary.by_severity[s] ?? 0} {s === 'info' ? 'note' : s}</span>
        ))}
        <span className="origin">{summary.by_origin.rule ?? 0} rule-based · {summary.by_origin.ai ?? 0} AI</span>
      </p>
      <div className={`ai-status ai-${ai.status}`} role="status">
        <p>{ai.status === 'ok' ? 'AI review ran.' : 'Rule-based results only.'} {ai.message}</p>
        {ai.checks_requiring_ai.length > 0 && (
          <details>
            <summary>Checks that need the AI review</summary>
            <ul>{ai.checks_requiring_ai.map((c) => <li key={c}>{c}</li>)}</ul>
          </details>
        )}
        <p className="hint">Source verification: {result.verification_provider}</p>
      </div>
    </section>
  )
}

export function FindingsPanel({ result, decisions, selectedId, conflicts, onSelect, onAccept, onReject, onClear }: Props) {
  const [cats, setCats] = useState<Set<Category>>(new Set(CATS))
  const [minSev, setMinSev] = useState<Severity>('info')
  const [origin, setOrigin] = useState<'all' | 'rule' | 'ai'>('all')
  const [status, setStatus] = useState<Status>('all')
  const [sort, setSort] = useState<Sort>('position')

  const visible = useMemo(() => {
    const fs = result.findings.filter(
      (f) =>
        cats.has(f.category) &&
        SEVERITY_RANK[f.severity] <= SEVERITY_RANK[minSev] &&
        (origin === 'all' || f.origin === origin) &&
        (status === 'all' || (status === 'pending' ? !decisions[f.id] : decisions[f.id]?.status === status)),
    )
    const pos = (f: Finding) => f.evidence?.start ?? Number.MAX_SAFE_INTEGER
    if (sort === 'severity') fs.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity] || pos(a) - pos(b))
    else if (sort === 'category') fs.sort((a, b) => CATS.indexOf(a.category) - CATS.indexOf(b.category) || SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
    else fs.sort((a, b) => pos(a) - pos(b))
    return fs
  }, [result.findings, cats, minSev, origin, status, sort, decisions])

  const toggle = (c: Category) => {
    const n = new Set(cats)
    if (n.has(c)) n.delete(c)
    else n.add(c)
    setCats(n)
  }

  const groups = sort === 'category' ? CATS.map((c) => [c, visible.filter((f) => f.category === c)] as const).filter(([, v]) => v.length) : [[null, visible] as const]

  return (
    <section className="findings" aria-label="Findings">
      <div className="filters">
        <div className="chips" role="group" aria-label="Show categories">
          {CATS.map((c) => (
            <button key={c} className={`chip cat-${c}`} aria-pressed={cats.has(c)} onClick={() => toggle(c)}>
              {CATEGORY_LABEL[c]} <span>{result.summary.by_category[c] ?? 0}</span>
            </button>
          ))}
        </div>
        <div className="selects">
          <label>Severity
            <select value={minSev} onChange={(e) => setMinSev(e.target.value as Severity)}>
              <option value="info">All</option>
              <option value="low">Low and above</option>
              <option value="medium">Medium and above</option>
              <option value="high">High only</option>
            </select>
          </label>
          <label>Source
            <select value={origin} onChange={(e) => setOrigin(e.target.value as typeof origin)}>
              <option value="all">All</option>
              <option value="rule">Rule-based</option>
              <option value="ai">AI assessment</option>
            </select>
          </label>
          <label>Status
            <select value={status} onChange={(e) => setStatus(e.target.value as Status)}>
              <option value="all">All</option>
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
          <label>Sort
            <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
              <option value="position">Position</option>
              <option value="severity">Severity</option>
              <option value="category">Category</option>
            </select>
          </label>
        </div>
      </div>
      <p className="count" aria-live="polite">Showing {visible.length} of {result.findings.length} findings</p>
      {visible.length === 0 && (
        <p className="empty">
          {result.findings.length === 0 ? 'No issues found by the checks that ran.' : 'No findings match these filters.'}
        </p>
      )}
      {groups.map(([c, fs]) => (
        <div key={c ?? 'all'} className="group">
          {c && <h3 className={`group-h cat-${c}`}>{CATEGORY_LABEL[c]}</h3>}
          {fs.map((f) => (
            <FindingCard
              key={f.id}
              f={f}
              decision={decisions[f.id]}
              selected={selectedId === f.id}
              conflictWith={wouldConflict(f, result.findings, decisions)}
              blocked={conflicts.has(f.id)}
              onSelect={() => onSelect(f.id)}
              onAccept={(t) => onAccept(f, t)}
              onReject={() => onReject(f)}
              onClear={() => onClear(f)}
            />
          ))}
        </div>
      ))}
    </section>
  )
}
