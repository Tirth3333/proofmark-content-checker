import { useState } from 'react'
import type { BrandBrief, IntentBrief, InternalLink } from '../types'

interface Props {
  intent: IntentBrief
  brand: BrandBrief
  onIntent: (i: IntentBrief) => void
  onBrand: (b: BrandBrief) => void
  useAI: boolean
  onUseAI: (v: boolean) => void
  aiAvailable: boolean
}

const list = (s: string) => s.split(/[,\n]/).map((x) => x.trim()).filter(Boolean)

function parseLinks(s: string): InternalLink[] {
  return s
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      const [url, ...rest] = l.split(/\s+/)
      return { url, anchor: rest.join(' ').replace(/^[-–|:]\s*/, '') }
    })
    .filter((l) => (l.url.startsWith('/') || /^https?:\/\//.test(l.url)) && l.anchor)
}

export function BriefPanel({ intent, brand, onIntent, onBrand, useAI, onUseAI, aiAvailable }: Props) {
  const [tab, setTab] = useState<'intent' | 'brand'>('intent')
  const [secondary, setSecondary] = useState(intent.secondary_keywords.join(', '))
  const [avoid, setAvoid] = useState(brand.avoid_terms.join(', '))
  const [links, setLinks] = useState(intent.internal_links.map((l) => `${l.url} ${l.anchor}`).join('\n'))

  // keep local text fields in sync when a demo brief is loaded
  const [seen, setSeen] = useState({ intent, brand })
  if (seen.intent !== intent || seen.brand !== brand) {
    setSeen({ intent, brand })
    if (seen.intent !== intent) {
      setSecondary(intent.secondary_keywords.join(', '))
      setLinks(intent.internal_links.map((l) => `${l.url} ${l.anchor}`).join('\n'))
    }
    if (seen.brand !== brand) setAvoid(brand.avoid_terms.join(', '))
  }

  const setI = <K extends keyof IntentBrief>(k: K, v: IntentBrief[K]) => onIntent({ ...intent, [k]: v })
  const setB = <K extends keyof BrandBrief>(k: K, v: BrandBrief[K]) => onBrand({ ...brand, [k]: v })

  return (
    <div className="brief">
      <p className="brief-lede">
        The brief is optional. Writing-quality and factuality checks always run; search-intent and brand-voice checks use only what you enter here.
      </p>
      <div className="seg" role="tablist" aria-label="Brief sections">
        <button role="tab" id="tab-intent" aria-selected={tab === 'intent'} aria-controls="panel-intent" onClick={() => setTab('intent')}>Search intent</button>
        <button role="tab" id="tab-brand" aria-selected={tab === 'brand'} aria-controls="panel-brand" onClick={() => setTab('brand')}>Brand voice</button>
      </div>

      {tab === 'intent' ? (
        <div role="tabpanel" id="panel-intent" aria-labelledby="tab-intent" className="fields">
          <label>Primary keyword or topic
            <input value={intent.primary_keyword} onChange={(e) => setI('primary_keyword', e.target.value)} placeholder="e.g. project management software" />
          </label>
          <label>Secondary keywords <span className="hint">comma-separated</span>
            <input value={secondary} onChange={(e) => { setSecondary(e.target.value); setI('secondary_keywords', list(e.target.value)) }} placeholder="free plan, integrations" />
          </label>
          <label>Target audience
            <input value={intent.audience} onChange={(e) => setI('audience', e.target.value)} placeholder="e.g. team leads at 5–20 person companies" />
          </label>
          <div className="two">
            <label>Search intent
              <select value={intent.search_intent} onChange={(e) => setI('search_intent', e.target.value as IntentBrief['search_intent'])}>
                <option value="">Not specified</option>
                <option value="informational">Informational</option>
                <option value="commercial">Commercial investigation</option>
                <option value="transactional">Transactional</option>
                <option value="navigational">Navigational</option>
              </select>
            </label>
            <label>Page type
              <select value={intent.page_type} onChange={(e) => setI('page_type', e.target.value as IntentBrief['page_type'])}>
                <option value="">Not specified</option>
                <option value="blog_post">Blog post</option>
                <option value="how_to">How-to guide</option>
                <option value="comparison">Comparison</option>
                <option value="product_page">Product page</option>
                <option value="landing_page">Landing page</option>
                <option value="glossary">Glossary / definition</option>
                <option value="other">Other</option>
              </select>
            </label>
          </div>
          <label>Content objective
            <input value={intent.objective} onChange={(e) => setI('objective', e.target.value)} placeholder="e.g. Get readers to start a free trial" />
          </label>
          <label>Internal pages you could link to <span className="hint">one per line: URL then anchor text</span>
            <textarea rows={3} value={links} onChange={(e) => { setLinks(e.target.value); setI('internal_links', parseLinks(e.target.value)) }} placeholder={'/pricing Pricing\n/guides/onboarding onboarding guide'} />
          </label>
        </div>
      ) : (
        <div role="tabpanel" id="panel-brand" aria-labelledby="tab-brand" className="fields">
          <label>Desired tone
            <select value={brand.tone} onChange={(e) => setB('tone', e.target.value as BrandBrief['tone'])}>
              <option value="">Not specified</option>
              <option value="formal">Formal: no contractions, slang or exclamations</option>
              <option value="conversational">Conversational: avoid stiff, legalistic wording</option>
              <option value="plain">Plain language: short words, no jargon</option>
              <option value="confident">Confident: no hedging or shouting</option>
            </select>
          </label>
          <label>Preferred terminology <span className="hint">one per line: “use X instead of Y” or “Y -&gt; X”</span>
            <textarea rows={3} value={brand.preferred_terms} onChange={(e) => setB('preferred_terms', e.target.value)} placeholder={'use customers instead of clients\nsign-up -> sign up'} />
          </label>
          <label>Words and phrases to avoid <span className="hint">comma-separated</span>
            <input value={avoid} onChange={(e) => { setAvoid(e.target.value); setB('avoid_terms', list(e.target.value)) }} placeholder="synergy, rockstar, cheap" />
          </label>
          <label>Brand guidelines <span className="hint">lines starting “Avoid:” or “Never use” are applied as rules</span>
            <textarea rows={4} value={brand.guidelines} onChange={(e) => setB('guidelines', e.target.value)} placeholder="Write like a calm, knowledgeable colleague. Avoid: hype, jargon" />
          </label>
          <label>Example of on-brand writing <span className="hint">40+ words; used to compare sentence length and style</span>
            <textarea rows={4} value={brand.example_content} onChange={(e) => setB('example_content', e.target.value)} />
          </label>
          <label className="check">
            <input type="checkbox" checked={brand.forbid_unsupported_claims} onChange={(e) => setB('forbid_unsupported_claims', e.target.checked)} />
            No unsupported promises or claims (flag superlatives and guarantees without evidence)
          </label>
        </div>
      )}

      <label className="check ai-toggle">
        <input type="checkbox" checked={useAI} onChange={(e) => onUseAI(e.target.checked)} disabled={!aiAvailable} />
        {aiAvailable ? 'Include AI semantic review' : 'AI semantic review unavailable: no provider configured on the server. Rule-based checks still run.'}
      </label>
    </div>
  )
}
