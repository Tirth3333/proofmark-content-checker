import type { Decisions, Finding } from '../types'

export interface AppliedEdit {
  findingId: string
  /** range in the ORIGINAL text */
  start: number
  end: number
  before: string
  after: string
  /** range of `after` in the REVISED text */
  revisedStart: number
  revisedEnd: number
}

export interface Conflict {
  findingId: string
  blockedBy: string
}

export interface ApplyResult {
  text: string
  edits: AppliedEdit[]
  conflicts: Conflict[]
}

/** The replacement that accepting this finding would apply, or null if it changes no text. */
export function replacementFor(f: Finding, decisions: Decisions): string | null {
  const d = decisions[f.id]
  if (d?.customText !== undefined) return d.customText
  return f.suggestion.replacement
}

export function isEditable(f: Finding): boolean {
  return f.evidence !== null
}

/**
 * Apply accepted suggestions to a copy of `original`. The original string is never
 * modified. Each edit only touches its own evidence span; when two accepted edits
 * overlap, the one earlier in the document wins and the other is reported as a conflict
 * rather than silently clobbering text.
 */
export function applyDecisions(original: string, findings: Finding[], decisions: Decisions): ApplyResult {
  const candidates = findings
    .filter((f) => decisions[f.id]?.status === 'accepted' && f.evidence)
    .map((f) => ({ f, repl: replacementFor(f, decisions) }))
    .filter((c): c is { f: Finding; repl: string } => c.repl !== null)
    .filter((c) => original.slice(c.f.evidence!.start, c.f.evidence!.end) === c.f.evidence!.text)
    .sort((a, b) => a.f.evidence!.start - b.f.evidence!.start || a.f.evidence!.end - b.f.evidence!.end)

  const chosen: { f: Finding; repl: string }[] = []
  const conflicts: Conflict[] = []
  for (const c of candidates) {
    const prev = chosen[chosen.length - 1]
    if (prev && c.f.evidence!.start < prev.f.evidence!.end) {
      conflicts.push({ findingId: c.f.id, blockedBy: prev.f.id })
      continue
    }
    chosen.push(c)
  }

  let out = ''
  let cursor = 0
  const edits: AppliedEdit[] = []
  for (const { f, repl } of chosen) {
    const ev = f.evidence!
    out += original.slice(cursor, ev.start)
    const revisedStart = out.length
    out += repl
    edits.push({ findingId: f.id, start: ev.start, end: ev.end, before: ev.text, after: repl, revisedStart, revisedEnd: out.length })
    cursor = ev.end
  }
  out += original.slice(cursor)
  return { text: out, edits, conflicts }
}

/** Accepted suggestions that would conflict with an already-accepted overlapping one. */
export function wouldConflict(f: Finding, findings: Finding[], decisions: Decisions): Finding | undefined {
  if (!f.evidence) return undefined
  return findings.find(
    (o) =>
      o.id !== f.id &&
      decisions[o.id]?.status === 'accepted' &&
      o.evidence &&
      replacementFor(o, decisions) !== null &&
      o.evidence.start < f.evidence!.end &&
      f.evidence!.start < o.evidence.end,
  )
}
