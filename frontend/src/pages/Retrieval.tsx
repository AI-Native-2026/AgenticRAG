import { useEffect, useRef, useState } from 'react'
import { Search, Image as ImageIcon, Type } from 'lucide-react'
import { api, searchByImage } from '@/api/client'
import { Empty, Loading } from '@/components/ui'
import AuthImage from '@/components/AuthImage'
import { toast } from '@/store/toast'
import type { KnowledgeBase, RetrievalResult } from '@/types'

interface SearchResp {
  candidates: number
  results: RetrievalResult[]
  recall_ms: number
  rerank_ms: number
}

export default function Retrieval() {
  const [mode, setMode] = useState<'text' | 'image'>('text')
  const [query, setQuery] = useState('iPhone 17 的电池容量是多少？')
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [kbId, setKbId] = useState('')
  const [topK, setTopK] = useState(30)
  const [topN, setTopN] = useState(5)
  const [rerank, setRerank] = useState(true)
  const [resp, setResp] = useState<SearchResp | null>(null)
  const [imgResp, setImgResp] = useState<{ results: RetrievalResult[]; query_image?: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<string>()
  const fileRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.get<{ knowledge_bases: KnowledgeBase[] }>('/v1/knowledge-bases')
      .then((r) => setKbs(r.knowledge_bases)).catch(() => {})
  }, [])

  async function run() {
    if (!query.trim()) return
    setLoading(true)
    try {
      const r = await api.post<SearchResp>('/v1/retrieval/search', {
        query, kb_id: kbId || null, top_k: topK, top_n: topN, rerank,
      })
      setResp(r)
    } catch (e: any) { toast.err(e.message) } finally { setLoading(false) }
  }

  async function onPickImage(file?: File) {
    if (!file) return
    setLoading(true)
    setPreview(URL.createObjectURL(file))
    try {
      const r = await searchByImage(file, topN)
      setImgResp(r)
    } catch (e: any) {
      toast.err(e.message)
    } finally {
      setLoading(false)
    }
  }

  const results = mode === 'text' ? (resp?.results || []) : (imgResp?.results || [])

  return (
    <>
      <div className="page-head">
        <div><h1>检索调试台</h1><div className="sub">混合检索、重排得分与以图搜图</div></div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '340px 1fr', alignItems: 'start' }}>
        <div className="card card-pad">
          <div className="seg mb" style={{ width: '100%' }}>
            <button className={mode === 'text' ? 'active' : ''} style={{ flex: 1 }} onClick={() => setMode('text')}>
              <Type size={13} /> 文本检索
            </button>
            <button className={mode === 'image' ? 'active' : ''} style={{ flex: 1 }} onClick={() => setMode('image')}>
              <ImageIcon size={13} /> 以图搜图
            </button>
          </div>

          {mode === 'text' ? (
            <>
              <div className="field">
                <label htmlFor="q">查询</label>
                <textarea id="q" className="input" rows={3} value={query} onChange={(e) => setQuery(e.target.value)} />
              </div>
              <div className="field">
                <label htmlFor="kb">知识库范围</label>
                <select id="kb" className="select" value={kbId} onChange={(e) => setKbId(e.target.value)}>
                  <option value="">全部知识库</option>
                  {kbs.map((k) => <option key={k.kb_id} value={k.kb_id}>{k.name}</option>)}
                </select>
              </div>
              <div className="row">
                <div className="field" style={{ flex: 1 }}><label htmlFor="tk">召回 Top-K</label>
                  <input id="tk" className="input" type="number" value={topK} onChange={(e) => setTopK(Number(e.target.value))} /></div>
                <div className="field" style={{ flex: 1 }}><label htmlFor="tn">重排 Top-N</label>
                  <input id="tn" className="input" type="number" value={topN} onChange={(e) => setTopN(Number(e.target.value))} /></div>
              </div>
              <label className="row" style={{ gap: 8, marginBottom: 12 }}>
                <input type="checkbox" checked={rerank} onChange={(e) => setRerank(e.target.checked)} /> 启用重排
              </label>
              <button className="btn btn-p" style={{ width: '100%' }} onClick={run} disabled={loading} data-testid="retrieval-run">
                <Search size={15} /> {loading ? '检索中…' : '检索'}
              </button>
            </>
          ) : (
            <>
              <div className="field">
                <label>上传图片</label>
                <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }}
                  onChange={(e) => onPickImage(e.target.files?.[0])} />
                <button className="btn btn-o" style={{ width: '100%' }} onClick={() => fileRef.current?.click()} disabled={loading}>
                  <ImageIcon size={15} /> {loading ? '检索中…' : '选择图片并检索'}
                </button>
              </div>
              {preview && (
                <div className="field">
                  <label>查询图</label>
                  <img src={preview} alt="query" style={{ width: '100%', borderRadius: 10, border: '1px solid var(--border)' }} />
                </div>
              )}
              <div className="note">以图搜图需要启用多模态 Embedding（EMBED_BACKEND=vl）。</div>
            </>
          )}
        </div>

        <div className="card">
          <div className="card-head">
            <h3>{mode === 'text' ? '检索结果' : '相似图片'}</h3>
            {mode === 'text' && resp && <span className="muted">召回 {resp.candidates} · 耗时 {resp.recall_ms}ms / 重排 {resp.rerank_ms}ms</span>}
            {mode === 'image' && imgResp && <span className="muted">共 {imgResp.results.length} 条</span>}
          </div>
          <div className="card-pad">
            {loading && results.length === 0 ? <Loading rows={3} /> :
              results.length === 0 ? <Empty title={mode === 'text' ? '输入查询并点击检索' : '上传一张图片开始检索'} /> : (
                results.map((r) => (
                  <div className="res" key={r.node_id}>
                    <div className="rh">
                      <span className="rank">{r.rank}</span>
                      <span className="tag">{r.modality === 'image' ? '图片' : r.source_type}</span>
                      <span className="tag">{r.doc_name}</span>
                      {r.page && <span className="tag">p{r.page}</span>}
                      <span className="spacer" />
                      {r.rerank_score != null && <span className={`score ${r.rerank_score > 0.7 ? 'hi' : ''}`}>重排 {Number(r.rerank_score).toFixed(3)}</span>}
                      {r.vector_score != null && <span className="score">向量 {Number(r.vector_score).toFixed(3)}</span>}
                    </div>
                    {r.modality === 'image' && (
                      <div style={{ marginBottom: 8 }}>
                        <AuthImage nodeId={r.node_id} alt={r.doc_name} style={{ maxWidth: 320, maxHeight: 220, borderRadius: 8, border: '1px solid var(--border)' }} />
                      </div>
                    )}
                    <div className="txt">{r.text}</div>
                  </div>
                ))
              )}
          </div>
        </div>
      </div>
    </>
  )
}
