import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Empty, Loading, Tabs } from '@/components/ui'
import { toast } from '@/store/toast'

export default function Observability() {
  const [tab, setTab] = useState('指标')
  const [metrics, setMetrics] = useState<any>(null)
  const [alerts, setAlerts] = useState<any[]>([])
  const [audit, setAudit] = useState<any[]>([])

  useEffect(() => {
    api.get<any>('/v1/metrics').then((r) => setMetrics(r.report)).catch((e) => toast.err(e.message))
    api.get<any>('/v1/alerts').then((r) => setAlerts(r.alerts)).catch(() => {})
    api.get<any>('/v1/audit?limit=100').then((r) => setAudit(r.audit)).catch(() => {})
  }, [])

  const m = metrics || {}

  return (
    <>
      <div className="page-head">
        <div><h1>观测</h1><div className="sub">指标、告警与审计日志</div></div>
      </div>

      <div className="grid g-4 mb">
        <div className="card stat"><div className="label">请求数</div><div className="val">{m.request_count ?? 0}</div></div>
        <div className="card stat"><div className="label">P95 生成延迟</div><div className="val">{m.latency_p95?.generate ? `${(m.latency_p95.generate / 1000).toFixed(2)}s` : '—'}</div></div>
        <div className="card stat"><div className="label">语义缓存命中率</div><div className="val">{m.semantic_cache_hit_rate ?? '—'}</div></div>
        <div className="card stat"><div className="label">Token 消耗</div><div className="val">{m.total_tokens ?? 0}</div></div>
      </div>

      <Tabs tabs={['指标', '告警', '审计']} active={tab} onChange={setTab} />

      {tab === '指标' && (
        <div className="card card-pad">
          {!metrics ? <Loading rows={4} /> : (
            <>
              <div style={{ fontWeight: 600, marginBottom: 12 }}>工具调用</div>
              {Object.keys(m.tool_calls || {}).length === 0 ? <Empty title="暂无工具调用" /> : (
                Object.entries(m.tool_calls).map(([k, v]: any) => (
                  <div className="bar-row mb" key={k}><span style={{ width: 120 }}>{k}</span><div className="bar"><i style={{ width: `${Math.min(100, v * 10)}%` }} /></div><b>{v}</b></div>
                ))
              )}
              <div className="divider" />
              <pre className="code">{JSON.stringify(m, null, 2)}</pre>
            </>
          )}
        </div>
      )}

      {tab === '告警' && (
        <div className="card">
          {alerts.length === 0 ? <Empty title="无告警" hint="指标正常" /> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>规则</th><th>指标</th><th>状态</th></tr></thead>
              <tbody>{alerts.map((a: any, i) => (
                <tr key={i}><td>{a.name || a.rule}</td><td className="mono">{a.metric} {a.op} {a.threshold}</td>
                  <td><span className={`pill ${a.firing ? 'err' : 'ok'}`}>{a.firing ? '触发' : '正常'}</span></td></tr>
              ))}</tbody>
            </table></div>
          )}
        </div>
      )}

      {tab === '审计' && (
        <div className="card">
          {audit.length === 0 ? <Empty title="暂无审计记录" /> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>时间</th><th>请求</th><th>角色</th><th>工具</th><th>结果</th><th>耗时</th></tr></thead>
              <tbody>{audit.map((a, i) => (
                <tr key={i}>
                  <td className="mono">{new Date((a.ts || 0) * 1000).toLocaleTimeString()}</td>
                  <td className="mono">{a.request_id}</td>
                  <td><span className="tag">{a.role}</span></td>
                  <td>{a.tool}</td>
                  <td><span className={`pill ${a.allowed && a.ok ? 'ok' : 'err'}`}>{a.allowed ? (a.ok ? '成功' : '失败') : '拒绝'}</span></td>
                  <td className="mono">{a.duration_ms}ms</td>
                </tr>
              ))}</tbody>
            </table></div>
          )}
        </div>
      )}
    </>
  )
}
