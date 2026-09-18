import { useEffect, useState } from 'react'
import { Plus, Layers } from 'lucide-react'
import { api } from '@/api/client'
import { Empty, Loading, Modal } from '@/components/ui'
import { toast } from '@/store/toast'
import type { Datasource, KnowledgeBase } from '@/types'

export default function KnowledgeBases() {
  const [items, setItems] = useState<KnowledgeBase[] | null>(null)
  const [datasources, setDatasources] = useState<Datasource[]>([])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', datasource_ids: [] as string[] })

  async function load() {
    try {
      const r = await api.get<{ knowledge_bases: KnowledgeBase[] }>('/v1/knowledge-bases')
      setItems(r.knowledge_bases)
      const d = await api.get<{ datasources: Datasource[] }>('/v1/datasources')
      setDatasources(d.datasources)
    } catch (e: any) { toast.err(e.message) }
  }
  useEffect(() => { load() }, [])

  async function create() {
    if (!form.name) return toast.err('请填写名称')
    try {
      await api.post('/v1/knowledge-bases', form)
      toast.ok('知识库已创建')
      setOpen(false); setForm({ name: '', description: '', datasource_ids: [] }); load()
    } catch (e: any) { toast.err(e.message) }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>知识库</h1><div className="sub">按业务域组织数据源，供 Agent 定向检索</div></div>
        <div className="actions"><button className="btn btn-p" onClick={() => setOpen(true)}><Plus size={15} /> 新建知识库</button></div>
      </div>

      {!items ? <div className="card card-pad"><Loading rows={4} /></div> :
        items.length === 0 ? <div className="card"><Empty title="还没有知识库" hint="创建知识库并绑定数据源" /></div> : (
          <div className="grid g-3">
            {items.map((kb) => (
              <div className="card card-pad" key={kb.kb_id}>
                <div className="row">
                  <span style={{ width: 38, height: 38, borderRadius: 11, background: 'linear-gradient(135deg,var(--accent),var(--accent-2))', color: '#fff', display: 'grid', placeItems: 'center' }}>
                    <Layers size={18} />
                  </span>
                  <div><div style={{ fontWeight: 700 }}>{kb.name}</div><div className="mono">{kb.slug}</div></div>
                </div>
                <div className="muted mt" style={{ minHeight: 36 }}>{kb.description || '—'}</div>
                <div className="divider" />
                <div className="row">
                  <span className="muted">{kb.datasource_count ?? kb.datasource_ids.length} 数据源</span>
                  <span className="spacer" />
                  <span className="muted">{kb.chunk_count ?? 0} chunks</span>
                </div>
              </div>
            ))}
          </div>
        )}

      <Modal open={open} title="新建知识库" onClose={() => setOpen(false)}
        footer={<><button className="btn btn-o" onClick={() => setOpen(false)}>取消</button><button className="btn btn-p" onClick={create}>创建</button></>}>
        <div className="field"><label htmlFor="kb-name">名称</label>
          <input id="kb-name" className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></div>
        <div className="field"><label htmlFor="kb-desc">描述</label>
          <textarea id="kb-desc" className="input" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        <div className="field"><label>绑定数据源</label>
          <div style={{ display: 'grid', gap: 8, maxHeight: 200, overflow: 'auto' }}>
            {datasources.map((d) => (
              <label key={d.ds_id} className="row" style={{ gap: 8 }}>
                <input type="checkbox" checked={form.datasource_ids.includes(d.ds_id)}
                  onChange={(e) => setForm({
                    ...form,
                    datasource_ids: e.target.checked
                      ? [...form.datasource_ids, d.ds_id]
                      : form.datasource_ids.filter((x) => x !== d.ds_id),
                  })} />
                <span>{d.name}</span><span className="tag">{d.type}</span>
              </label>
            ))}
            {datasources.length === 0 && <span className="muted">暂无数据源</span>}
          </div>
        </div>
      </Modal>
    </>
  )
}
