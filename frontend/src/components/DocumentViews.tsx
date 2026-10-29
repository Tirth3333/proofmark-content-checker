import { Fragment, useEffect, useMemo, useRef } from 'react'
import type { Finding } from '../types'
import { CATEGORY_LABEL } from '../types'
import { buildSegments } from '../lib/text'
import type { ApplyResult } from '../lib/suggestions'

interface ReviewProps {
  text: string
  findings: Finding[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ReviewDocument({ text, findings, selectedId, onSelect }: ReviewProps) {
  const byId = useMemo(() => new Map(findings.map((f) => [f.id, f])), [findings])
  const segs = useMemo(() => buildSegments(text, findings), [text, findings])
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!selectedId || !ref.current) return
    const el = ref.current.querySelector<HTMLElement>(`[data-ids~="${CSS.escape(selectedId)}"]`)
    el?.scrollIntoView({ block: 'center', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  }, [selectedId])

  const docLevel = findings.filter((f) => !f.evidence)

  return (
    <div className="review">
      <div className="legend" aria-label="Highlight legend">
        {(['factuality', 'quality', 'intent', 'brand'] as const).map((c) => (
          <span key={c} className={`legend-i mk-${c}`}><span className="swatch" />{CATEGORY_LABEL[c]}</span>
        ))}
      </div>
      <div ref={ref} className="manuscript manuscript-read" aria-label="Original text with highlighted findings">
        {segs.map((s) => {
          if (!s.findingIds.length) return <Fragment key={s.start}>{s.text}</Fragment>
          const first = byId.get(s.findingIds[0])!
          const isSel = selectedId !== null && s.findingIds.includes(selectedId)
          const label = s.findingIds.map((id) => byId.get(id)!.title).join('; ')
          return (
            <mark
              key={s.start}
              className={`mk mk-${s.category} ${s.findingIds.length > 1 ? 'mk-multi' : ''} ${isSel ? 'mk-sel' : ''}`}
              data-ids={s.findingIds.join(' ')}
              tabIndex={0}
              role="button"
              aria-label={`${label}. Text: ${s.text}`}
              title={label}
              onClick={() => onSelect(isSel && s.findingIds.length > 1 ? s.findingIds[(s.findingIds.indexOf(selectedId!) + 1) % s.findingIds.length] : first.id)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault()
                  onSelect(first.id)
                }
              }}
            >
              {s.text}
            </mark>
          )
        })}
      </div>
      {docLevel.length > 0 && (
        <p className="hint doc-level">{docLevel.length} finding(s) apply to the document as a whole and are listed in the findings panel.</p>
      )}
    </div>
  )
}

interface CompareProps {
  original: string
  applied: ApplyResult
  onCopy: () => void
}

export function CompareView({ original, applied, onCopy }: CompareProps) {
  const left: React.ReactNode[] = []
  const right: React.ReactNode[] = []
  let o = 0
  let r = 0
  applied.edits.forEach((e, i) => {
    left.push(original.slice(o, e.start))
    left.push(<del key={'d' + i} className="chg-del">{e.before}</del>)
    o = e.end
    right.push(applied.text.slice(r, e.revisedStart))
    right.push(e.after ? <ins key={'i' + i} className="chg-ins">{e.after}</ins> : <span key={'i' + i} className="chg-gap" aria-label="text removed" />)
    r = e.revisedEnd
  })
  left.push(original.slice(o))
  right.push(applied.text.slice(r))

  return (
    <div className="compare">
      <p className="compare-note">
        {applied.edits.length === 0
          ? 'No changes accepted yet. Accept suggestions in the findings panel and they appear here; the original stays untouched.'
          : `${applied.edits.length} accepted change(s) applied to a copy. The original on the left is never modified.`}
        {applied.conflicts.length > 0 && ` ${applied.conflicts.length} accepted change(s) overlap an earlier one and were not applied.`}
      </p>
      <div className="compare-grid">
        <section aria-labelledby="orig-h">
          <h3 id="orig-h">Original</h3>
          <div className="manuscript manuscript-read small">{left}</div>
        </section>
        <section aria-labelledby="rev-h">
          <div className="rev-head">
            <h3 id="rev-h">Revised</h3>
            <button className="btn btn-quiet btn-sm" onClick={onCopy}>Copy revised text</button>
          </div>
          <div className="manuscript manuscript-read small" data-testid="revised-text">{right}</div>
        </section>
      </div>
    </div>
  )
}
