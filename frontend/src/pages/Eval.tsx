import { useEffect, useState } from 'react'
import { Play, Plus, Save, Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import { Empty, Loading, Modal } from '@/components/ui'
import { toast } from '@/store/toast'

export default function Eval() {
  const [items, setItems] = useState<any[] | null>(null)
  const [report, setReport] = useState<any>(null)
  const [baseline, setBaseline] = useState<any>(null)
  const [running, setRunning] = useState(false)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ query: '', golden_docs: '', golden_keywords: '', kb_id: '' })
  const [kbs, setKbs] = useState<any[]>([])

  async function load() {
    try {
      const r = await api.get<any>('/v1/eval/set')
      setItems(r.items)
    } catch (e: any) { toast.err(e.message) }
  }
  useEffect(() => {
    load()
    api.get<any>('/v1/eval/baseline').then(setBaseline).catch(() => {})
    api.get<any>('/v1/knowledge-bases').then((r) => setKbs(r.knowledge_bases)).catch(() => {})
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

  async function addItem() {
    if (!form.query.trim()) return toast.err('请填写 Query')
    try {
      await api.post('/v1/eval/set', {
        query: form.query.trim(),
        golden_docs: form.golden_docs.split(',').map((s) => s.trim()).filter(Boolean),
        golden_keywords: form.golden_keywords.split(',').map((s) => s.trim()).filter(Boolean),
        kb_id: form.kb_id || null,
      })
      toast.ok('已新增评测项')
      setOpen(false); setForm({ query: '', golden_docs: '', golden_keywords: '', kb_id: '' }); setReport(null); load()
    } catch (e: any) { toast.err(e.message) }
  }

  async function removeItem(i: number) {
    if (!confirm('确认删除该评测项？')) return
    try {
      await api.del(`/v1/eval/set/${i}`)
      toast.ok('已删除'); setReport(null); load()
    } catch (e: any) { toast.err(e.message) }
  }

  const delta = (cur?: number, base?: number) =>
    cur == null || base == null ? null : (cur - base).toFixed(3)

  return (
    <>
      <div className="page-head">
        <div><h1>评测</h1><div className="sub">评测集、检索指标与基线对比</div></div>
        <div className="actions">
          <button className="btn btn-o" onClick={() => setOpen(true)}><Plus size={15} /> 新增评测项</button>
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
          items.length === 0 ? <Empty title="暂无评测项" hint="点击右上角「新增评测项」添加" /> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>#</th><th>Query</th><th>Golden Docs</th><th>命中</th><th>Rank</th><th></th></tr></thead>
              <tbody>{items.map((it, i) => {
                const d = report?.details?.[i]
                return (
                  <tr key={i}>
                    <td className="mono">{i + 1}</td>
                    <td>{it.query}</td>
                    <td className="mono">{(it.golden_docs || []).join(', ') || '—'}</td>
                    <td>{d ? <span className={`pill ${d.hit ? 'ok' : 'err'}`}>{d.hit ? '命中' : '未命中'}</span> : '—'}</td>
                    <td className="mono">{d?.rank ?? '—'}</td>
                    <td><button className="btn btn-d btn-xs" onClick={() => removeItem(i)}><Trash2 size={12} /></button></td>
                  </tr>
                )
              })}</tbody>
            </table></div>
          )}
      </div>

      <Modal open={open} title="新增评测项" onClose={() => setOpen(false)}
        footer={<><button className="btn btn-o" onClick={() => setOpen(false)}>取消</button><button className="btn btn-p" onClick={addItem}>添加</button></>}>
        <div className="field"><label htmlFor="ev-q">Query</label>
          <textarea id="ev-q" className="input" rows={2} value={form.query} onChange={(e) => setForm({ ...form, query: e.target.value })} placeholder="如：iPhone 17 的电池容量是多少？" /></div>
        <div className="field"><label htmlFor="ev-d">Golden Docs（逗号分隔）</label>
          <input id="ev-d" className="input" value={form.golden_docs} onChange={(e) => setForm({ ...form, golden_docs: e.target.value })} placeholder="apple_iphone_17.md" /></div>
        <div className="field"><label htmlFor="ev-k">Golden Keywords（逗号分隔，可选）</label>
          <input id="ev-k" className="input" value={form.golden_keywords} onChange={(e) => setForm({ ...form, golden_keywords: e.target.value })} /></div>
        <div className="field"><label htmlFor="ev-scope">检索范围</label>
          <select id="ev-scope" className="select" value={form.kb_id} onChange={(e) => setForm({ ...form, kb_id: e.target.value })}>
            <option value="">当前租户全部知识（默认）</option>
            {kbs.map((k) => <option key={k.kb_id} value={k.kb_id}>{k.name}</option>)}
          </select></div>
        <div className="note">评测默认按登录租户隔离；选择知识库可进一步限定到该知识库的数据源。</div>
      </Modal>
    </>
  )
}
