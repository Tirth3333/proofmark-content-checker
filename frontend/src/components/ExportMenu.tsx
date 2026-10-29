import { useEffect, useRef, useState } from 'react'

export interface ExportAction {
  id: string
  label: string
  detail: string
  run: () => void | Promise<void>
}

export function ExportMenu({ actions, disabled }: { actions: ExportAction[]; disabled: boolean }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', close)
    }
  }, [open])

  return (
    <div className="export" ref={ref}>
      <button className="btn" aria-haspopup="menu" aria-expanded={open} disabled={disabled} onClick={() => setOpen(!open)}
        title={disabled ? 'Analyze content to enable exports' : undefined}>
        Export
      </button>
      {open && (
        <div className="menu" role="menu">
          {actions.map((a) => (
            <button
              key={a.id}
              role="menuitem"
              disabled={busy !== null}
              onClick={async () => {
                setBusy(a.id)
                try {
                  await a.run()
                } finally {
                  setBusy(null)
                  setOpen(false)
                }
              }}
            >
              <span>{busy === a.id ? 'Preparing…' : a.label}</span>
              <small>{a.detail}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
