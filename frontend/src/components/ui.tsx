import React, { useEffect } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useToast, type ToastKind } from '@/store/toast'

/* ---------- Modal ---------- */
export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  width,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  width?: number
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && open && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <>
      <div className="mask show" onClick={onClose} />
      <div className="modal show" style={width ? { width } : undefined} role="dialog" aria-modal="true" aria-label={title}>
        <div className="mh">
          <h3>{title}</h3>
          <button className="btn btn-g btn-sm" onClick={onClose} aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        <div className="mb">{children}</div>
        {footer && <div className="mf">{footer}</div>}
      </div>
    </>,
    document.body,
  )
}

/* ---------- Drawer ---------- */
export function Drawer({
  open,
  title,
  onClose,
  children,
  footer,
}: {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && open && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [open, onClose])

  return createPortal(
    <>
      <div className={`mask ${open ? 'show' : ''}`} onClick={onClose} />
      <aside className={`drawer ${open ? 'show' : ''}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="dh">
          <h3>{title}</h3>
          <button className="btn btn-g btn-sm" onClick={onClose} aria-label="关闭">
            <X size={16} />
          </button>
        </div>
        <div className="db">{children}</div>
        {footer && <div className="df">{footer}</div>}
      </aside>
    </>,
    document.body,
  )
}

/* ---------- Toasts ---------- */
const toastIcon: Record<ToastKind, string> = { ok: '✓', err: '✕', info: 'i' }

export function ToastHost() {
  const toasts = useToast((s) => s.toasts)
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span className="ti">{toastIcon[t.kind]}</span>
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  )
}

/* ---------- Status pill ---------- */
const statusMap: Record<string, { cls: string; text: string }> = {
  success: { cls: 'ok', text: '成功' },
  ready: { cls: 'ok', text: '已就绪' },
  connected: { cls: 'ok', text: '已连接' },
  running: { cls: 'run', text: '运行中' },
  syncing: { cls: 'run', text: '同步中' },
  pending: { cls: 'warn', text: '等待中' },
  created: { cls: 'mute', text: '未连接' },
  failed: { cls: 'err', text: '失败' },
  error: { cls: 'err', text: '错误' },
}

export function StatusPill({ status }: { status: string }) {
  const s = statusMap[status] || { cls: 'mute', text: status }
  return <span className={`pill ${s.cls}`}>{s.text}</span>
}

/* ---------- Sparkline ---------- */
export function Sparkline({ values, color = '#6366f1', width = 90, height = 34 }: {
  values: number[]; color?: string; width?: number; height?: number
}) {
  const pad = 3
  const max = Math.max(...values)
  const min = Math.min(...values)
  const rng = max - min || 1
  const pts = values.map((v, i) => [
    pad + ((width - pad * 2) * i) / (values.length - 1),
    height - pad - ((height - pad * 2) * (v - min)) / rng,
  ])
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
  const area = `${line} L ${width - pad} ${height} L ${pad} ${height} Z`
  return (
    <svg width={width} height={height} aria-hidden="true">
      <path d={area} fill={color} opacity=".1" />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" />
    </svg>
  )
}

/* ---------- Tabs ---------- */
export function Tabs({ tabs, active, onChange }: { tabs: string[]; active: string; onChange: (t: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t} className={`tab ${active === t ? 'active' : ''}`} role="tab" aria-selected={active === t} onClick={() => onChange(t)}>
          {t}
        </button>
      ))}
    </div>
  )
}

/* ---------- Empty / Loading ---------- */
export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="empty">
      <h4>{title}</h4>
      {hint && <div>{hint}</div>}
    </div>
  )
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div style={{ display: 'grid', gap: 10 }}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="skeleton" style={{ width: `${100 - i * 12}%` }} />
      ))}
    </div>
  )
}

/* ---------- Progress bar ---------- */
export function Progress({ value, tone }: { value: number; tone?: 'ok' | 'warn' | 'err' }) {
  const v = Math.max(0, Math.min(100, value || 0))
  return (
    <div className={`bar ${tone || ''}`}>
      <i style={{ width: `${v}%` }} />
    </div>
  )
}
