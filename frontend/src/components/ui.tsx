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

/* ---------- Donut ---------- */
export function Donut({
  segments,
  size = 132,
  thickness = 14,
  centerLabel,
  centerValue,
}: {
  segments: { value: number; color: string; label?: string }[]
  size?: number
  thickness?: number
  centerLabel?: string
  centerValue?: string
}) {
  const total = segments.reduce((s, x) => s + Math.max(0, x.value), 0)
  const r = (size - thickness) / 2
  const c = 2 * Math.PI * r
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={centerLabel || '占比图'}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--track-bg)" strokeWidth={thickness} />
      {total > 0 &&
        segments.map((s, i) => {
          const frac = Math.max(0, s.value) / total
          const dash = frac * c
          const el = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={thickness}
              strokeDasharray={`${dash} ${c - dash}`}
              strokeDashoffset={-offset}
              strokeLinecap="butt"
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            />
          )
          offset += dash
          return el
        })}
      {(centerValue || centerLabel) && (
        <>
          <text x="50%" y="47%" textAnchor="middle" dominantBaseline="middle" fontSize="20" fontWeight="750" fill="var(--text)">
            {centerValue}
          </text>
          <text x="50%" y="63%" textAnchor="middle" dominantBaseline="middle" fontSize="11" fill="var(--muted)">
            {centerLabel}
          </text>
        </>
      )}
    </svg>
  )
}

/* ---------- Line / Area chart ---------- */
export function LineChart({
  series,
  labels,
  height = 200,
  yFormat,
}: {
  series: { name: string; color: string; values: number[] }[]
  labels: string[]
  height?: number
  yFormat?: (v: number) => string
}) {
  const w = 760
  const padL = 44
  const padR = 14
  const padT = 14
  const padB = 26
  const n = labels.length || 1
  const all = series.flatMap((s) => s.values)
  const max = Math.max(1, ...all)
  const x = (i: number) => padL + ((w - padL - padR) * i) / Math.max(1, n - 1)
  const y = (v: number) => padT + (height - padT - padB) * (1 - v / max)
  const ticks = 4

  return (
    <div style={{ width: '100%', overflow: 'hidden' }}>
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none" role="img">
        {Array.from({ length: ticks + 1 }).map((_, i) => {
          const gy = padT + ((height - padT - padB) * i) / ticks
          const val = max * (1 - i / ticks)
          return (
            <g key={i}>
              <line x1={padL} y1={gy} x2={w - padR} y2={gy} stroke="var(--border)" strokeWidth="1" />
              <text x={padL - 8} y={gy + 3} textAnchor="end" fontSize="10" fill="var(--muted)">
                {yFormat ? yFormat(val) : Math.round(val)}
              </text>
            </g>
          )
        })}
        {labels.map((lb, i) => {
          const step = Math.ceil(n / 7)
          if (i % step !== 0 && i !== n - 1) return null
          return (
            <text key={i} x={x(i)} y={height - 8} textAnchor="middle" fontSize="10" fill="var(--muted)">
              {lb}
            </text>
          )
        })}
        {series.map((s) => {
          const pts = s.values.map((v, i) => [x(i), y(v)] as const)
          const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ')
          const area = `${line} L ${x(n - 1).toFixed(1)} ${height - padB} L ${x(0).toFixed(1)} ${height - padB} Z`
          return (
            <g key={s.name}>
              <path d={area} fill={s.color} opacity=".08" />
              <path d={line} fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
            </g>
          )
        })}
      </svg>
    </div>
  )
}

/* ---------- Chart legend ---------- */
export function Legend({ items }: { items: { name: string; color: string }[] }) {
  return (
    <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 12, color: 'var(--muted)' }}>
      {items.map((it) => (
        <span key={it.name} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <i style={{ width: 9, height: 9, borderRadius: 3, background: it.color, display: 'inline-block' }} />
          {it.name}
        </span>
      ))}
    </div>
  )
}
