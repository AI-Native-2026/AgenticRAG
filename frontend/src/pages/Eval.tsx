import { useEffect, useState } from 'react'
import { Play, Save } from 'lucide-react'
import { api } from '@/api/client'
import { Empty, Loading } from '@/components/ui'
import { toast } from '@/store/toast'

export default function Eval() {
  const [items, setItems] = useState<any[] | null>(null)
  const [report, setReport] = useState<any>(null)
  const [baseline, setBaseline] = useState<any>(null)
  const [running, setRunning] = useState(false)

  useEffect(() => {
    api.get<any>('/v1/eval/set').then((r) => setItems(r.items)).catch((e) => toast.err(e.message))
    api.get<any>('/v1/eval/baseline').then(setBaseline).catch(() => {})
  }, [])

  async function run() {
    setRunning(true)
    try {
      const r = await api.post<any>('/v1/eval/run')
      setReport(r.report)
      toast.ok('评测完成')
    } catch (e: any) { toast.err(e.message) } finally { setRunning(false) }
  }

  async function saveBaseline() {
    if (!report) return toast.err('请先运行评测')
    try {
      await api.post('/v1/eval/baseline', report)
      setBaseline(report)
      toast.ok('基线已保存')
    } catch (e: any) { toast.err(e.message) }
  }

  const delta = (cur?: number, base?: number) =>
    cur == null || base == null ? null : (cur - base).toFixed(3)

  return (
    <>
      <div className="page-head">
        <div><h1>评测</h1><div className="sub">评测集、检索指标与基线对比</div></div>
        <div className="actions">
          <button className="btn btn-o" onClick={saveBaseline}><Save size={15} /> 保存基线</button>
          <button className="btn btn-p" onClick={run} disabled={running}><Play size={15} /> {running ? '运行中…' : '运行评测'}</button>
        </div>
      </div>

      <div className="grid g-4 mb">
        <div className="card stat"><div className="label">Hit Rate</div><div className="val">{report?.hit_rate ?? baseline?.hit_rate ?? '—'}</div>
          {delta(report?.hit_rate, baseline?.hit_rate) && <div className="delta">Δ {delta(report?.hit_rate, baseline?.hit_rate)}</div>}</div>
        <div className="card stat"><div className="label">MRR</div><div className="val">{report?.mrr ?? baseline?.mrr ?? '—'}</div>
          {delta(report?.mrr, baseline?.mrr) && <div className="delta">Δ {delta(report?.mrr, baseline?.mrr)}</div>}</div>
        <div className="card stat"><div className="label">评测条数</div><div className="val">{report?.count ?? items?.length ?? 0}</div></div>
        <div className="card stat"><div className="label">基线</div><div className="val" style={{ fontSize: 18 }}>{baseline?.hit_rate != null ? `HR ${baseline.hit_rate}` : '未保存'}</div></div>
      </div>

      <div className="card">
        <div className="card-head"><h3>评测集</h3><span className="muted">{items?.length ?? 0} 条</span></div>
        {!items ? <div className="card-pad"><Loading rows={4} /></div> :
          items.length === 0 ? <Empty title="未找到评测集" hint="在 backend/data/eval_set.jsonl 中配置" /> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>#</th><th>Query</th><th>Golden Docs</th><th>命中</th><th>Rank</th></tr></thead>
              <tbody>{items.map((it, i) => {
                const d = report?.details?.[i]
                return (
                  <tr key={i}>
                    <td className="mono">{i + 1}</td>
                    <td>{it.query}</td>
                    <td className="mono">{(it.golden_docs || []).join(', ')}</td>
                    <td>{d ? <span className={`pill ${d.hit ? 'ok' : 'err'}`}>{d.hit ? '命中' : '未命中'}</span> : '—'}</td>
                    <td className="mono">{d?.rank ?? '—'}</td>
                  </tr>
                )
              })}</tbody>
            </table></div>
          )}
      </div>
    </>
  )
}
