import { useState } from 'react'
import { extractUrl, ApiError } from '../api'
import { textStats } from '../lib/text'

interface Props {
  text: string
  onChange: (t: string) => void
  maxChars: number
  analyzing: boolean
  canReset: boolean
  stale: boolean
  onAnalyze: () => void
  onClear: () => void
  onReset: () => void
  onLoadDemo: () => void
  onExtracted: (text: string, url: string, title: string) => void
}

export function Editor(p: Props) {
  const [url, setUrl] = useState('')
  const [fetching, setFetching] = useState(false)
  const [urlError, setUrlError] = useState<string | null>(null)
  const [urlOk, setUrlOk] = useState<string | null>(null)
  const s = textStats(p.text)
  const over = p.text.length > p.maxChars
  const empty = !p.text.trim()

  async function fetchUrl(e: React.FormEvent) {
    e.preventDefault()
    setUrlError(null)
    setUrlOk(null)
    const u = url.trim()
    if (!/^https?:\/\/\S+\.\S+/i.test(u)) {
      setUrlError('Enter a full public URL starting with http:// or https://.')
      return
    }
    setFetching(true)
    try {
      const r = await extractUrl(u)
      p.onExtracted(r.text, r.url, r.title)
      setUrlOk(`Extracted ${r.characters.toLocaleString()} characters${r.title ? ` from “${r.title}”` : ''}. Review the text below before analyzing.`)
    } catch (err) {
      setUrlError(err instanceof ApiError ? err.message : 'Extraction failed.')
    } finally {
      setFetching(false)
    }
  }

  return (
    <div className="editor">
      <form className="url-row" onSubmit={fetchUrl} noValidate aria-label="Extract text from a web page">
        <label htmlFor="url" className="visually-hidden">Public page URL</label>
        <input
          id="url"
          type="url"
          inputMode="url"
          placeholder="Paste a public page URL to extract its text (optional)"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          aria-invalid={!!urlError}
          aria-describedby="url-msg"
        />
        <button type="submit" className="btn" disabled={fetching || !url.trim()}>
          {fetching ? 'Extracting…' : 'Extract text'}
        </button>
      </form>
      <p id="url-msg" className={urlError ? 'msg msg-error' : 'msg msg-ok'} role={urlError ? 'alert' : 'status'}>
        {urlError ?? urlOk ?? ''}
      </p>

      <label htmlFor="content" className="visually-hidden">Content to review</label>
      <textarea
        id="content"
        className="manuscript"
        value={p.text}
        onChange={(e) => p.onChange(e.target.value)}
        placeholder={'Paste an article, blog post or page copy here.\n\nMarkdown headings (# Heading) and blank lines between paragraphs help the structure checks.'}
        spellCheck
        aria-describedby="content-stats content-limit"
      />

      <div className="editor-foot">
        <p id="content-stats" className="stats" aria-live="polite">
          <span>{s.words.toLocaleString()} words</span>
          <span>{s.characters.toLocaleString()} characters</span>
          <span>{s.paragraphs.toLocaleString()} paragraphs</span>
        </p>
        <div className="actions">
          <button type="button" className="btn btn-quiet" onClick={p.onLoadDemo}>Load demo article</button>
          <button type="button" className="btn btn-quiet" onClick={p.onClear} disabled={empty}>Clear</button>
          <button type="button" className="btn btn-quiet" onClick={p.onReset} disabled={!p.canReset} title="Put the last analyzed text back in the editor">
            Reset to analyzed text
          </button>
          <button type="button" className="btn btn-primary" onClick={p.onAnalyze} disabled={empty || over || p.analyzing}>
            {p.analyzing ? 'Analyzing…' : p.stale ? 'Re-analyze' : 'Analyze'}
          </button>
        </div>
      </div>
      {over && (
        <p id="content-limit" className="msg msg-error" role="alert">
          The text is {p.text.length.toLocaleString()} characters; the limit is {p.maxChars.toLocaleString()}. Split it and analyze it in parts.
        </p>
      )}
    </div>
  )
}
