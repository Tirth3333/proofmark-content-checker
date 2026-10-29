import type { Category, Finding } from '../types'
import { SEVERITY_RANK } from '../types'

const WORD_RE = /[A-Za-z0-9][A-Za-z0-9'’-]*/g

export function textStats(text: string) {
  const words = text.match(WORD_RE)?.length ?? 0
  const paragraphs = text.split(/\n\s*\n/).filter((p) => p.trim()).length
  return { words, characters: text.length, paragraphs }
}

export interface HighlightSegment {
  start: number
  end: number
  text: string
  findingIds: string[]
  /** category of the most severe finding covering this segment */
  category: Category | null
}

/** Split text into segments at every finding boundary, so overlapping findings render correctly. */
export function buildSegments(text: string, findings: Finding[]): HighlightSegment[] {
  const spans = findings.filter((f) => f.evidence && f.evidence.end > f.evidence.start)
  const cuts = new Set<number>([0, text.length])
  for (const f of spans) {
    cuts.add(Math.max(0, Math.min(text.length, f.evidence!.start)))
    cuts.add(Math.max(0, Math.min(text.length, f.evidence!.end)))
  }
  const points = [...cuts].sort((a, b) => a - b)
  const segs: HighlightSegment[] = []
  for (let i = 0; i < points.length - 1; i++) {
    const s = points[i]
    const e = points[i + 1]
    if (e <= s) continue
    const covering = spans
      .filter((f) => f.evidence!.start <= s && f.evidence!.end >= e)
      .sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])
    segs.push({
      start: s,
      end: e,
      text: text.slice(s, e),
      findingIds: covering.map((f) => f.id),
      category: covering[0]?.category ?? null,
    })
  }
  return segs
}
