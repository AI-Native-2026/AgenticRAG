import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Layers, FileText, Inbox, Cpu } from 'lucide-react'
import { api } from '@/api/client'
import { Loading, Sparkline, StatusPill } from '@/components/ui'
import { toast } from '@/store/toast'

interface Summary {
  stats: { documents: number; chunks: number; datasources: number; knowledge_bases: number }
  jobs: Record<string, number>
  metrics: { request_count: number; latency_p95_generate?: number; tool_calls: Record<string, number>; total_tokens: number }
  recent_jobs: any[]
}

export default function Dashboard() {
  const [data, setData] = useState<Summary | null>(null)
  const nav = useNavigate()

  useEffect(() => {
    api.get<Summary>('/v1/dashboard/summary').then(setData).catch((e) => toast.err(e.message))
  }, [])

  if (!data) return <div className="card card-pad"><Loading rows={4} /></div>

  const s = data.stats
  const cards = [
    { label: '知识库', value: s.knowledge_bases, unit: '个', color: '#6366f1', icon: Layers, spark: [3, 3, 4, 4, 5, 5, Math.max(1, s.knowledge_bases)] },
    { label: '文档 / Chunk', value: s.chunks, unit: 'chunks', color: '#16a34a', icon: FileText, spark: [8, 9, 8.5, 10, 11, 11.5, Math.max(1, s.chunks / 1000)] },
    { label: '数据源', value: s.datasources, unit: '个', color: '#2563eb', icon: Inbox, spark: [2, 3, 3, 4, 5, 6, Math.max(1, s.datasources)] },
    { label: '请求数（今日）', value: data.metrics.request_count, unit: '次', color: '#d97706', icon: Cpu, spark: [6, 7, 6.4, 7.2, 6.8, 6, Math.max(1, data.metrics.request_count)] },
  ]

  return (
    <>
      <div className="page-head">
        <div>
          <h1>概览</h1>
          <div className="sub">知识中台运行状态与关键指标</div>
        </div>
        <div className="actions">
          <button className="btn btn-o" onClick={() => nav('/datasources')}>接入数据源</button>
          <button className="btn btn-p" onClick={() => nav('/chat')}>开始对话</button>
        </div>
      </div>

      <div className="grid g-4">
        {cards.map((c) => (
          <div className="card stat" key={c.label}>
            <div className="label" style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
              <span style={{ width: 24, height: 24, borderRadius: 7, background: 'var(--accent-soft)', color: c.color, display: 'grid', placeItems: 'center' }}>
                <c.icon size={14} />
              </span>
              {c.label}
            </div>
            <div className="val">
              {c.value.toLocaleString()} <small>{c.unit}</small>
            </div>
            <Sparkline values={c.spark} color={c.color} />
          </div>
        ))}
      </div>

      <div className="grid g-2-1 mt">
        <div className="card">
          <div className="card-head"><h3>最近入库任务</h3></div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>数据源</th><th>模式</th><th>结果</th><th>状态</th></tr></thead>
              <tbody>
                {data.recent_jobs.map((j) => (
                  <tr key={j.job_id} className="clickable" onClick={() => nav('/jobs')}>
                    <td className="mono">{j.datasource_id}</td>
                    <td><span className="tag">{j.mode}</span></td>
                    <td className="mono">{j.chunks} chunks</td>
                    <td><StatusPill status={j.status} /></td>
                  </tr>
                ))}
                {data.recent_jobs.length === 0 && (
                  <tr><td colSpan={4} className="muted">暂无任务</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
        <div className="card">
          <div className="card-head"><h3>任务状态</h3></div>
          <div className="card-pad" style={{ display: 'grid', gap: 12 }}>
            {Object.entries(data.jobs).map(([k, v]) => (
              <div className="bar-row" key={k}>
                <span style={{ width: 64 }}>{k}</span>
                <div className="bar"><i style={{ width: `${Math.min(100, v * 12)}%` }} /></div>
                <b>{v}</b>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
