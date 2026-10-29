import { render, screen, within, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { ORIGINAL, RESPONSE } from './fixtures'

const health = { status: 'ok', ai: { enabled: false, provider: 'none', message: 'none' }, verification: { enabled: false, provider: 'none' }, limits: { max_chars: 500 } }

function mockFetch(handlers: Record<string, (body: unknown) => Response>) {
  const calls: { url: string; body: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : undefined
    calls.push({ url, body })
    const key = Object.keys(handlers).find((k) => url.endsWith(k))
    return key ? handlers[key](body) : new Response('{}', { status: 404 })
  }))
  return calls
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

async function analyzeFixture(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByLabelText('Content to review'))
  await user.paste(ORIGINAL)
  await user.click(screen.getByRole('button', { name: 'Analyze' }))
  await screen.findByText(RESPONSE.summary.headline)
}

afterEach(() => vi.unstubAllGlobals())

describe('App', () => {
  it('disables Analyze for empty input and shows live counts', async () => {
    mockFetch({ '/api/health': () => json(health) })
    const user = userEvent.setup()
    render(<App />)
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeDisabled()
    await user.type(screen.getByLabelText('Content to review'), 'Two words')
    expect(screen.getByText('2 words')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeEnabled()
  })

  it('blocks content over the server limit', async () => {
    mockFetch({ '/api/health': () => json(health) })
    const user = userEvent.setup()
    render(<App />)
    await screen.findByText('Rule-based mode')
    await user.click(screen.getByLabelText('Content to review'))
    await user.paste('x'.repeat(501))
    expect(screen.getByRole('alert')).toHaveTextContent('the limit is 500')
    expect(screen.getByRole('button', { name: 'Analyze' })).toBeDisabled()
  })

  it('analyzes, highlights evidence, and accepts / rejects / undoes / restores', async () => {
    const calls = mockFetch({ '/api/health': () => json(health), '/api/analyze': () => json(RESPONSE) })
    const user = userEvent.setup()
    render(<App />)
    await analyzeFixture(user)

    const req = calls.find((c) => c.url.endsWith('/api/analyze'))!
    expect((req.body as { text: string }).text).toBe(ORIGINAL)

    // highlights in the original
    const doc = screen.getByLabelText('Original text with highlighted findings')
    expect(doc.textContent).toBe(ORIGINAL)
    expect(within(doc).getAllByRole('button').length).toBeGreaterThan(3)

    // accept the terminology fix
    const card = screen.getByText('Use preferred terminology').closest('article')!
    await user.click(within(card).getByRole('button', { name: 'Accept change' }))
    expect(within(card).getByText('Applied')).toBeInTheDocument()

    // reject the filler fix
    const filler = screen.getByText('Filler language').closest('article')!
    await user.click(within(filler).getByRole('button', { name: 'Reject' }))
    expect(within(filler).getByText('Rejected')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Compare (1)' }))
    expect(screen.getByTestId('revised-text').textContent).toBe(ORIGINAL.replace('clients', 'customers'))

    // undo reverts the last decision (the rejection), not the accepted change
    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(within(screen.getByText('Filler language').closest('article')!).queryByText('Rejected')).toBeNull()
    expect(screen.getByTestId('revised-text').textContent).toContain('customers')

    // restore original clears everything; original text was never changed
    await user.click(screen.getByRole('button', { name: 'Restore original' }))
    expect(screen.getByTestId('revised-text').textContent).toBe(ORIGINAL)
    await user.click(screen.getByRole('tab', { name: 'Write' }))
    expect(screen.getByLabelText('Content to review')).toHaveValue(ORIGINAL)
  })

  it('lets the user write their own fix for an advisory finding', async () => {
    mockFetch({ '/api/health': () => json(health), '/api/analyze': () => json(RESPONSE) })
    const user = userEvent.setup()
    render(<App />)
    await analyzeFixture(user)
    const card = screen.getByText('Needs verification: statistic').closest('article')!
    await user.click(within(card).getByRole('button', { name: 'Write my own fix' }))
    const box = within(card).getByLabelText('Your replacement for the highlighted text')
    await user.clear(box)
    await user.type(box, 'Revenue grew in 2024.')
    await user.click(within(card).getByRole('button', { name: 'Apply my edit' }))
    await user.click(screen.getByRole('tab', { name: 'Compare (1)' }))
    expect(screen.getByTestId('revised-text').textContent).toContain('Revenue grew in 2024.')
  })

  it('filters findings by category and severity', async () => {
    mockFetch({ '/api/health': () => json(health), '/api/analyze': () => json(RESPONSE) })
    const user = userEvent.setup()
    render(<App />)
    await analyzeFixture(user)
    expect(screen.getByText('Showing 6 of 6 findings')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Writing quality/ }))
    expect(screen.getByText('Showing 4 of 6 findings')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Severity'), 'high')
    expect(screen.getByText('Showing 1 of 6 findings')).toBeInTheDocument()
    expect(screen.getByText('Needs verification: statistic')).toBeInTheDocument()
  })

  it('shows rule-based mode and the checks that need AI', async () => {
    mockFetch({ '/api/health': () => json(health), '/api/analyze': () => json(RESPONSE) })
    const user = userEvent.setup()
    render(<App />)
    await analyzeFixture(user)
    expect(screen.getByText(/Rule-based results only/)).toBeInTheDocument()
    expect(screen.getByText('Weak explanations')).toBeInTheDocument()
  })

  it('shows the server error message when analysis fails', async () => {
    mockFetch({ '/api/health': () => json(health), '/api/analyze': () => json({ detail: 'AI provider exploded.' }, 500) })
    const user = userEvent.setup()
    render(<App />)
    await user.type(screen.getByLabelText('Content to review'), 'Some text here.')
    await user.click(screen.getByRole('button', { name: 'Analyze' }))
    expect(await screen.findByText('AI provider exploded.')).toBeInTheDocument()
  })

  it('shows URL extraction errors and fills the editor on success', async () => {
    let fail = true
    mockFetch({
      '/api/health': () => json(health),
      '/api/extract': () => (fail ? json({ detail: "This site's robots.txt does not permit automated access." }, 403) : json({ url: 'https://example.com/a', title: 'A', text: 'Extracted body text.', characters: 20 })),
    })
    const user = userEvent.setup()
    render(<App />)
    const url = screen.getByLabelText('Public page URL')
    await user.type(url, 'not a url')
    await user.click(screen.getByRole('button', { name: 'Extract text' }))
    expect(await screen.findByText(/Enter a full public URL/)).toBeInTheDocument()
    await user.clear(url)
    await user.type(url, 'https://example.com/a')
    await user.click(screen.getByRole('button', { name: 'Extract text' }))
    expect(await screen.findByText(/robots.txt/)).toBeInTheDocument()
    fail = false
    await user.click(screen.getByRole('button', { name: 'Extract text' }))
    await waitFor(() => expect(screen.getByLabelText('Content to review')).toHaveValue('Extracted body text.'))
  })

  it('loads the labelled demo article and brief', async () => {
    mockFetch({ '/api/health': () => json(health) })
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByRole('button', { name: 'Load demo article' }))
    expect(screen.getByText('Demonstration content.')).toBeInTheDocument()
    expect((screen.getByLabelText('Content to review') as HTMLTextAreaElement).value).toContain('TaskNest')
  })

  it('exports the findings CSV and report', async () => {
    mockFetch({ '/api/health': () => json(health), '/api/analyze': () => json(RESPONSE) })
    const created: Blob[] = []
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: (b: Blob) => { created.push(b); return 'blob:x' }, revokeObjectURL: () => {} }))
    const user = userEvent.setup()
    render(<App />)
    await analyzeFixture(user)
    await user.click(screen.getByRole('button', { name: 'Export' }))
    await user.click(screen.getByRole('menuitem', { name: /Findings \(\.csv\)/ }))
    await user.click(screen.getByRole('button', { name: 'Export' }))
    await user.click(screen.getByRole('menuitem', { name: /Audit report \(\.md\)/ }))
    expect(created).toHaveLength(2)
    expect(await created[0].text()).toContain('id,category,severity')
    expect(await created[1].text()).toContain('# Content audit report')
  })
})
