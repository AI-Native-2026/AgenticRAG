import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import { api } from '@/api/client'
import { Empty, Loading } from '@/components/ui'
import { toast } from '@/store/toast'
import type { Chunk, DocumentItem } from '@/types'

export default function Documents() {
  const [docs, setDocs] = useState<DocumentItem[] | null>(null)
  const [active, setActive] = useState<DocumentItem | null>(null)
  const [chunks, setChunks] = useState<Chunk[] | null>(null)

  async function load() {
    try {
      const r = await api.get<{ documents: DocumentItem[] }>('/v1/documents')
      setDocs(r.documents)
    } catch (e: any) { toast.err(e.message) }
  }
  useEffect(() => { load() }, [])

  useEffect(() => {
    if (!active) return
    setChunks(null)
    api.get<{ chunks: Chunk[] }>(`/v1/documents/${active.ref_doc_id}`)
      .then((r) => setChunks(r.chunks))
      .catch((e) => { toast.err(e.message); setChunks([]) })
  }, [active])

  async function remove(d: DocumentItem) {
    if (!confirm(`确认删除文档「${d.doc_name}」及其 ${d.chunks} 个 chunk？`)) return
    try {
      await api.del(`/v1/documents/${d.ref_doc_id}`)
      toast.ok('已删除')
      setActive(null); load()
    } catch (e: any) { toast.err(e.message) }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>文档浏览</h1><div className="sub">查看文档切分结果、元数据与来源</div></div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '320px 1fr', alignItems: 'start' }}>
        <div className="card" style={{ maxHeight: 640, overflow: 'auto' }}>
          <div className="card-head"><h3>文档</h3><span className="muted" style={{ marginLeft: 'auto' }}>{docs?.length ?? 0}</span></div>
          <div className="card-pad" style={{ display: 'grid', gap: 4 }}>
            {!docs ? <Loading /> : docs.length === 0 ? <Empty title="暂无文档" /> :
              docs.map((d) => (
                <div key={d.ref_doc_id} className={`list-item ${active?.ref_doc_id === d.ref_doc_id ? 'active' : ''}`} onClick={() => setActive(d)}>
                  <div className="t">{d.doc_name}</div>
                  <div className="m"><span className="tag">{d.source_type}</span><span>{d.chunks} chunks</span></div>
                </div>
              ))}
          </div>
        </div>

        <div className="card">
          {!active ? <Empty title="选择左侧文档查看 chunk" /> : (
            <>
              <div className="card-head">
                <h3>{active.doc_name}</h3>
                <span className="tag">v{active.doc_version}</span>
                <div className="right">
                  <button className="btn btn-d btn-xs" onClick={() => remove(active)}><Trash2 size={12} /> 删除</button>
                </div>
              </div>
              <div className="card-pad">
                {!chunks ? <Loading /> : chunks.length === 0 ? <Empty title="无 chunk" /> : (
                  <div style={{ display: 'grid', gap: 10 }}>
                    {chunks.map((c) => (
                      <div className="res" key={c.node_id}>
                        <div className="rh">
                          <span className="rank">{c.chunk_idx}</span>
                          {c.metadata?.page && <span className="tag">page {c.metadata.page}</span>}
                          {c.metadata?.table && <span className="tag">{c.metadata.table}</span>}
                          {c.metadata?.heading && <span className="tag">{c.metadata.heading}</span>}
                          <span className="spacer" />
                          <span className="mono">{c.node_id}</span>
                        </div>
                        <div className="txt">{c.text}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}
