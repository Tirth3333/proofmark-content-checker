import type { AnalyzeResponse, BrandBrief, IntentBrief } from './types'

const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function post<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError('Could not reach the analysis server. Check that the backend is running.', 0)
  }
  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status}).`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') detail = j.detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status)
  }
  return res.json() as Promise<T>
}

export interface AnalyzePayload {
  text: string
  intent: IntentBrief
  brand: BrandBrief
  use_ai: boolean
  verify_sources: boolean
}

export const analyzeContent = (p: AnalyzePayload, signal?: AbortSignal) => post<AnalyzeResponse>('/analyze', p, signal)

export const extractUrl = (url: string, signal?: AbortSignal) =>
  post<{ url: string; title: string; text: string; characters: number }>('/extract', { url }, signal)

export interface Health {
  ai: { enabled: boolean; provider: string; message: string }
  verification: { enabled: boolean; provider: string }
  limits: { max_chars: number }
}

export async function getHealth(): Promise<Health | null> {
  try {
    const r = await fetch(`${BASE}/api/health`)
    return r.ok ? ((await r.json()) as Health) : null
  } catch {
    return null
  }
}
