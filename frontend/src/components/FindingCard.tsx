import { useState } from 'react'
import type { Decision, Finding } from '../types'
import { CATEGORY_LABEL } from '../types'
import { verificationLabel } from '../lib/exports'

interface Props {
  f: Finding
  decision?: Decision
  selected: boolean
  conflictWith?: Finding
  blocked?: boolean
  onSelect: () => void
  onAccept: (customText?: string) => void
  onReject: () => void
  onClear: () => void
}

const SEV_LABEL = { high: 'High', medium: 'Medium', low: 'Low', info: 'Note' } as const

export function FindingCard({ f, decision, selected, conflictWith, blocked, onSelect, onAccept, onReject, onClear }: Props) {
  const [editing, setEditing] = useState(false)
  const initial = decision?.customText ?? f.suggestion.replacement ?? f.evidence?.text ?? ''
  const [draft, setDraft] = useState(initial)
  const hasChange = f.suggestion.replacement !== null || decision?.customText !== undefined
  const replacement = decision?.customText ?? f.suggestion.replacement
  const status = decision?.status

  return (
    <article
      className={`card cat-${f.category} ${selected ? 'is-selected' : ''} ${status ? 'is-' + status : ''}`}
      aria-labelledby={`t-${f.id}`}
      data-finding={f.id}
    >
      <button className="card-head" onClick={onSelect} aria-expanded={selected} aria-controls={`b-${f.id}`}>
        <span className={`sev sev-${f.severity}`} aria-label={`Severity: ${SEV_LABEL[f.severity]}`}>{SEV_LABEL[f.severity]}</span>
        <span id={`t-${f.id}`} className="card-title">{f.title}</span>
        {status && <span className={`state state-${status}`}>{status === 'accepted' ? (hasChange ? 'Applied' : 'Addressed') : 'Rejected'}</span>}
      </button>

      <div className="card-meta">
        <span className="cat-tag">{CATEGORY_LABEL[f.category]}</span>
        <span>{f.origin === 'ai' ? 'AI assessment' : 'Rule-based'}</span>
        <span>{f.confidence[0].toUpperCase() + f.confidence.slice(1)} confidence</span>
      </div>

      {f.evidence ? (
        <blockquote className="evidence" onClick={onSelect}>
          {f.evidence.text.length > 280 ? f.evidence.text.slice(0, 280) + '…' : f.evidence.text}
        </blockquote>
      ) : (
        <p className="evidence-note">{f.evidence_note || 'Document-level finding.'}</p>
      )}

      <div id={`b-${f.id}`} className="card-body" hidden={!selected}>
        <p>{f.explanation}</p>
        {f.related.length > 0 && (
          <p className="related">
            Also see: {f.related.slice(0, 3).map((r, i) => <q key={i}>{r.text.length > 90 ? r.text.slice(0, 90) + '…' : r.text}</q>)}
          </p>
        )}
        <p className="suggest"><strong>Suggestion.</strong> {f.suggestion.note}</p>
        {f.verification && (
          <div className={`verify v-${f.verification.status}`}>
            <p><strong>{verificationLabel(f.verification.status)}.</strong> {f.verification.note}</p>
            {f.verification.suggested_source_types.length > 0 && (
              <p className="hint">Check against: {f.verification.suggested_source_types.join('; ')}.</p>
            )}
            {f.verification.sources.length > 0 && (
              <ul className="sources">
                {f.verification.sources.map((s) => (
                  <li key={s.url}>
                    <a href={s.url} target="_blank" rel="noopener noreferrer nofollow">{s.title || s.url}</a>
                    {s.explanation && <span>: {s.explanation}</span>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>

      {f.evidence && replacement !== null && replacement !== undefined && !editing && (
        <p className="diff" aria-label="Proposed change">
          <del>{f.evidence.text.length > 120 ? f.evidence.text.slice(0, 120) + '…' : f.evidence.text}</del>
          <span aria-hidden="true"> → </span>
          {replacement === '' ? <em className="removed">remove</em> : <ins>{replacement}</ins>}
        </p>
      )}

      {editing && f.evidence && (
        <div className="custom-edit">
          <label htmlFor={`e-${f.id}`}>Your replacement for the highlighted text</label>
          <textarea id={`e-${f.id}`} rows={3} value={draft} onChange={(e) => setDraft(e.target.value)} autoFocus />
          <div className="row">
            <button className="btn btn-primary btn-sm" onClick={() => { onAccept(draft); setEditing(false) }}>Apply my edit</button>
            <button className="btn btn-quiet btn-sm" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      )}

      {conflictWith && status !== 'accepted' && (
        <p className="msg msg-warn">Overlaps an accepted change (“{conflictWith.title}”). Accepting this will be skipped until that one is undone.</p>
      )}
      {blocked && <p className="msg msg-warn">Not applied: it overlaps an earlier accepted change.</p>}

      {!editing && (
        <div className="card-actions">
          {status ? (
            <button className="btn btn-quiet btn-sm" onClick={onClear}>Undo decision</button>
          ) : (
            <>
              <button className="btn btn-accept btn-sm" onClick={() => onAccept()}>
                {hasChange ? 'Accept change' : 'Mark addressed'}
              </button>
              <button className="btn btn-quiet btn-sm" onClick={onReject}>Reject</button>
              {f.evidence && (
                <button className="btn btn-quiet btn-sm" onClick={() => { setDraft(initial); setEditing(true) }}>Write my own fix</button>
              )}
            </>
          )}
        </div>
      )}
    </article>
  )
}
