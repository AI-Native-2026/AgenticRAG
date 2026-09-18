import { useEffect, useRef, useState } from 'react'
import { Layers, ChevronDown } from 'lucide-react'

interface KB { kb_id: string; name: string; datasource_count?: number; datasource_ids?: string[] }

export default function KnowledgeScope({
  kbs,
  value,
  onChange,
}: {
  kbs: KB[]
  value: string[]
  onChange: (ids: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    const k = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', h)
    document.addEventListener('keydown', k)
    return () => {
      document.removeEventListener('mousedown', h)
      document.removeEventListener('keydown', k)
    }
  }, [])

  const all = value.length === 0
  const label = all
    ? '全部知识库'
    : value.length === 1
      ? (kbs.find((k) => k.kb_id === value[0])?.name || '1 个知识库')
      : `${value.length} 个知识库`

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id])
  }

  return (
    <div className="scope" ref={ref}>
      <button className="scope-btn" onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox" aria-expanded={open} data-testid="scope-toggle">
        <Layers size={14} />
        <span className="scope-lbl">检索范围</span>
        <b>{label}</b>
        <ChevronDown size={13} className={`scope-caret ${open ? 'up' : ''}`} />
      </button>

      {open && (
        <div className="scope-panel" role="listbox" aria-label="选择知识库">
          <label className="scope-item">
            <input type="checkbox" checked={all} onChange={() => onChange([])} />
            <span>全部知识库</span>
          </label>
          <div className="scope-sep" />
          {kbs.map((k) => (
            <label key={k.kb_id} className={`scope-item ${value.includes(k.kb_id) ? 'on' : ''}`}>
              <input type="checkbox" checked={value.includes(k.kb_id)} onChange={() => toggle(k.kb_id)} />
              <span>{k.name}</span>
              <span className="spacer" />
              <span className="muted">{k.datasource_count ?? k.datasource_ids?.length ?? 0}</span>
            </label>
          ))}
          {kbs.length === 0 && <div className="muted" style={{ padding: '8px 10px' }}>暂无知识库</div>}
        </div>
      )}
    </div>
  )
}
