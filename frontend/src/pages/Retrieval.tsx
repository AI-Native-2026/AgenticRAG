import { useEffect, useState } from 'react'
import { Search } from 'lucide-react'
import { api } from '@/api/client'
import { Empty, Loading } from '@/components/ui'
import { toast } from '@/store/toast'
import type { KnowledgeBase, RetrievalResult } from '@/types'

interface SearchResp {
  candidates: number
  results: RetrievalResult[]
  recall_ms: number
  rerank_ms: number
}

export default function Retrieval() {
  const [query, setQuery] = useState('iPhone 17 的电池容量是多少？')
  const [kbs, setKbs] = useState<KnowledgeBase[]>([])
  const [kbId, setKbId] = useState('')
  const [topK, setTopK] = useState(30)
  const [topN, setTopN] = useState(5)
  const [rerank, setRerank] = useState(true)
  const [resp, setResp] = useState<SearchResp | null>(null)
  const [loading, setLoading] = useState(false)

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

  return (
    <>
      <div className="page-head">
        <div><h1>检索调试台</h1><div className="sub">查看混合检索、重排得分与命中来源</div></div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: '340px 1fr', alignItems: 'start' }}>
        <div className="card card-pad">
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
        </div>

        <div className="card">
          <div className="card-head">
            <h3>检索结果</h3>
            {resp && <span className="muted">召回 {resp.candidates} · 耗时 {resp.recall_ms}ms / 重排 {resp.rerank_ms}ms</span>}
          </div>
          <div className="card-pad">
            {!resp ? <Empty title="输入查询并点击检索" /> : resp.results.length === 0 ? <Empty title="无命中结果" /> : (
              resp.results.map((r) => (
                <div className="res" key={r.node_id}>
                  <div className="rh">
                    <span className="rank">{r.rank}</span>
                    <span className="tag">{r.source_type}</span>
                    <span className="tag">{r.doc_name}</span>
                    {r.table && <span className="tag">{r.table}</span>}
                    {r.page && <span className="tag">p{r.page}</span>}
                    <span className="spacer" />
                    {r.rrf_score != null && <span className="score">rrf {Number(r.rrf_score).toFixed(3)}</span>}
                    {r.rerank_score != null && <span className={`score ${r.rerank_score > 0.7 ? 'hi' : ''}`}>重排 {Number(r.rerank_score).toFixed(3)}</span>}
                  </div>
                  <div className="txt">{r.text}</div>
                </div>
              ))
            )}
            {loading && <Loading rows={3} />}
          </div>
        </div>
      </div>
    </>
  )
}
