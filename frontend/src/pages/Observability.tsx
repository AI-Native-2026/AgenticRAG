import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { Empty, Legend, LineChart, Loading, Tabs } from '@/components/ui'
import { toast } from '@/store/toast'

interface TS {
  bucket: string
  buckets: string[]
  series: {
    requests: number[]
    tool_calls: number[]
    tokens: number[]
    latency_p50: number[]
    latency_p95: number[]
    retrieval_p95: number[]
  }
}

const COLORS = { a: '#6366f1', b: '#8b5cf6', c: '#16a34a', d: '#d97706', e: '#0891b2' }

export default function Observability() {
  const [tab, setTab] = useState('时序')
  const [metrics, setMetrics] = useState<any>(null)
  const [ts, setTs] = useState<TS | null>(null)
  const [days, setDays] = useState(7)
  const [alerts, setAlerts] = useState<any[]>([])
  const [audit, setAudit] = useState<any[]>([])

  useEffect(() => {
    api.get<any>('/v1/metrics').then((r) => setMetrics(r.report)).catch((e) => toast.err(e.message))
    api.get<any>('/v1/alerts').then((r) => setAlerts(r.alerts)).catch(() => {})
    api.get<any>('/v1/audit?limit=100').then((r) => setAudit(r.audit)).catch(() => {})
  }, [])

  useEffect(() => {
    api.get<TS>(`/v1/metrics/timeseries?days=${days}&bucket=${days > 3 ? 'day' : 'hour'}`)
      .then(setTs).catch(() => setTs(null))
  }, [days])

  const m = metrics || {}
  const labels = (ts?.buckets || []).map((b) => b.slice(5))

  const charts: { key: keyof TS['series']; title: string; color: string; fmt?: (v: number) => string }[] = [
    { key: 'requests', title: '请求数', color: COLORS.a },
    { key: 'latency_p50', title: '生成延迟 P50 (ms)', color: COLORS.a, fmt: (v) => `${Math.round(v)}` },
    { key: 'latency_p95', title: '生成延迟 P95 (ms)', color: COLORS.b, fmt: (v) => `${Math.round(v)}` },
    { key: 'retrieval_p95', title: '检索延迟 P95 (ms)', color: COLORS.e, fmt: (v) => `${Math.round(v)}` },
    { key: 'tool_calls', title: '工具调用', color: COLORS.c },
    { key: 'tokens', title: 'Token 消耗', color: COLORS.d },
  ]

  return (
    <>
      <div className="page-head">
        <div><h1>观测</h1><div className="sub">指标、时序趋势、告警与审计</div></div>
        <div className="actions">
          <div className="seg">
            {[1, 3, 7].map((d) => (
              <button key={d} className={days === d ? 'active' : ''} onClick={() => setDays(d)}>近 {d} 天</button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid g-4 mb">
        <div className="card stat"><div className="label">请求数</div><div className="val">{m.request_count ?? 0}</div></div>
        <div className="card stat"><div className="label">P95 生成延迟</div><div className="val">{m.latency_p95?.generate ? `${(m.latency_p95.generate / 1000).toFixed(2)}s` : '—'}</div></div>
        <div className="card stat"><div className="label">语义缓存命中率</div><div className="val">{m.semantic_cache_hit_rate != null ? Number(m.semantic_cache_hit_rate).toFixed(2) : '—'}</div></div>
        <div className="card stat"><div className="label">Token 消耗</div><div className="val">{m.total_tokens ?? 0}</div></div>
      </div>

      <Tabs tabs={['时序', '指标', '告警', '审计']} active={tab} onChange={setTab} />

      {tab === '时序' && (
        <div className="grid g-2">
          {charts.map((c) => (
            <div className="card" key={c.key}>
              <div className="card-head">
                <h3>{c.title}</h3>
                <div className="right"><Legend items={[{ name: c.title, color: c.color }]} /></div>
              </div>
              <div className="card-pad">
                {!ts ? <Loading rows={3} /> : (
                  <LineChart
                    height={190}
                    labels={labels}
                    yFormat={c.fmt}
                    series={[{ name: c.title, color: c.color, values: ts.series[c.key] }]}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {tab === '指标' && (
        <div className="grid g-2-1">
          <div className="card">
            <div className="card-head"><h3>工具调用分布</h3></div>
            <div className="card-pad">
              {!metrics ? <Loading /> : Object.keys(m.tool_calls || {}).length === 0 ? <Empty title="暂无工具调用" /> : (
                Object.entries(m.tool_calls).map(([k, v]: any) => {
                  const max = Math.max(...Object.values(m.tool_calls as Record<string, number>), 1)
                  return (
                    <div className="bar-row mb" key={k}>
                      <span style={{ width: 120 }}>{k}</span>
                      <div className="bar"><i style={{ width: `${(v / max) * 100}%` }} /></div>
                      <b>{v}</b>
                    </div>
                  )
                })
              )}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h3>用量</h3></div>
            <div className="card-pad">
              <div className="kv"><span className="k">总 Token</span><span className="v">{m.total_tokens ?? 0}</span></div>
              {Object.entries(m.tokens_by_tenant || {}).map(([k, v]: any) => (
                <div className="kv" key={k}><span className="k">租户 {k}</span><span className="v">{v}</span></div>
              ))}
            </div>
          </div>
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
