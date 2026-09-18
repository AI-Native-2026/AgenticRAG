import { useEffect, useRef, useState } from 'react'
import { Plus, Send, Trash2, Image as ImageIcon } from 'lucide-react'
import { api, chatStream, searchByImage } from '@/api/client'
import { toast } from '@/store/toast'
import MarkdownView from '@/components/MarkdownView'
import KnowledgeScope from '@/components/KnowledgeScope'
import AuthImage from '@/components/AuthImage'

interface ToolStep { tool: string; ok?: boolean; duration_ms?: number; detail?: string }
interface Source { node_id: string; doc_name: string; modality?: string; page?: number | string; score?: number }
interface ImageHit { node_id: string; doc_name: string; modality?: string; vector_score?: number }
interface Message {
  role: 'user' | 'bot'
  content: string
  steps: ToolStep[]
  sources?: Source[]
  image?: string
  imageResults?: ImageHit[]
  streaming?: boolean
}
interface SessionMeta { session_id: string; title: string; last: number; messages: number }

const SESSION_KEY = 'kr_session'

function newSessionId() {
  return `web-${Date.now().toString(36)}`
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: '你好，我是 **小K**，你的知识中台助手。可以帮你检索知识库、查询数据库，或生成数据图表。', steps: [] },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem(SESSION_KEY) || newSessionId())
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [kbs, setKbs] = useState<any[]>([])
  const [selectedKbs, setSelectedKbs] = useState<string[]>([])
  const [imgBusy, setImgBusy] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const imgRef = useRef<HTMLInputElement>(null)

  function scrollDown() {
    requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight })
  }

  const updateBot = (fn: (msg: Message) => Message) =>
    setMessages((m) => m.map((msg, i) => (i === m.length - 1 ? fn(msg) : msg)))

  function persist(id: string) {
    localStorage.setItem(SESSION_KEY, id)
    setSessionId(id)
  }

  async function loadSessions() {
    try {
      const r = await api.get<{ sessions: SessionMeta[] }>('/v1/sessions')
      setSessions(r.sessions)
    } catch { /* ignore */ }
  }

  async function loadHistory(id: string) {
    try {
      const r = await api.get<{ messages: { role: string; content: string }[] }>(`/v1/sessions/${id}`)
      if (r.messages.length) {
        setMessages(r.messages.map((m) => ({ role: m.role === 'user' ? 'user' : 'bot', content: m.content, steps: [] })))
      } else {
        setMessages([{ role: 'bot', content: '已开启新会话。', steps: [] }])
      }
    } catch {
      setMessages([{ role: 'bot', content: '已开启新会话。', steps: [] }])
    }
  }

  useEffect(() => {
    loadSessions()
    loadHistory(sessionId)
    api.get<{ knowledge_bases: any[] }>('/v1/knowledge-bases')
      .then((r) => setKbs(r.knowledge_bases)).catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function switchSession(id: string) {
    if (busy) return
    persist(id)
    await loadHistory(id)
    scrollDown()
  }

  function startNew() {
    const id = newSessionId()
    persist(id)
    setMessages([{ role: 'bot', content: '已开启新会话。', steps: [] }])
    loadSessions()
  }

  async function removeSession(id: string, e: React.MouseEvent) {
    e.stopPropagation()
    try {
      await api.del(`/v1/sessions/${id}`)
      toast.ok('会话已删除')
      if (id === sessionId) startNew()
      loadSessions()
    } catch (err: any) { toast.err(err.message) }
  }

  async function send() {
    const q = input.trim()
    if (!q || busy) return
    setInput('')
    setBusy(true)
    setMessages((m) => [...m, { role: 'user', content: q, steps: [] }, { role: 'bot', content: '', steps: [], streaming: true }])
    scrollDown()

    try {
      await chatStream(q, sessionId, (event, data) => {
        if (event === 'token') {
          updateBot((msg) => ({ ...msg, content: msg.content + (data.content || '') }))
          scrollDown()
        } else if (event === 'retrieval') {
          updateBot((msg) => ({ ...msg, steps: [...msg.steps, { tool: 'kb_search', detail: `召回 ${data.n_candidates} 条 · ${data.duration_ms}ms` }] }))
        } else if (event === 'rerank') {
          updateBot((msg) => ({ ...msg, steps: [...msg.steps, { tool: 'rerank', detail: `重排 ${data.n_output} 条 · ${data.duration_ms}ms` }] }))
        } else if (event === 'sql') {
          updateBot((msg) => ({ ...msg, steps: [...msg.steps, { tool: 'sql_query', detail: `${data.row_count} 行` }] }))
        } else if (event === 'sources') {
          updateBot((msg) => ({ ...msg, sources: data.items || [] }))
        } else if (event === 'tool_call') {
          updateBot((msg) => {
            const steps = [...msg.steps]
            const last = steps[steps.length - 1]
            if (last && last.tool === data.tool) last.ok = data.ok
            else steps.push({ tool: data.tool, ok: data.ok, duration_ms: data.duration_ms })
            return { ...msg, steps }
          })
        } else if (event === 'error') {
          toast.err(data.message || '对话出错')
        }
      }, { kbIds: selectedKbs })
    } catch (e: any) {
      toast.err(e.message)
    } finally {
      updateBot((msg) => ({ ...msg, streaming: false }))
      setBusy(false)
      scrollDown()
      loadSessions()
    }
  }

  async function onPickImage(file?: File) {
    if (!file) return
    const url = URL.createObjectURL(file)
    setMessages((m) => [...m,
      { role: 'user', content: '', steps: [], image: url },
      { role: 'bot', content: '', steps: [], streaming: true }])
    scrollDown()
    setImgBusy(true)
    try {
      const r = await searchByImage(file, 6)
      const hits: ImageHit[] = r.results || []
      updateBot((msg) => ({
        ...msg,
        streaming: false,
        content: hits.length ? `为你找到 ${hits.length} 张相似图片：` : '未找到相似图片。',
        imageResults: hits,
      }))
    } catch (e: any) {
      updateBot((msg) => ({ ...msg, streaming: false, content: `以图搜图失败：${e.message}` }))
      toast.err(e.message)
    } finally {
      setImgBusy(false)
      scrollDown()
    }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Agent 对话</h1><div className="sub">多轮对话 · 工具调用 · 图表报表 · 引用溯源</div></div>
        <div className="actions"><button className="btn btn-o" onClick={startNew}><Plus size={15} /> 新建会话</button></div>
      </div>

      <div className="chat-wrap">
        <div className="card chat-main">
          <div className="chat-scroll" ref={scrollRef}>
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="av">{m.role === 'user' ? 'A' : 'K'}</div>
                <div>
                  <div className={`bub ${m.role === 'bot' ? 'md' : ''}`}>
                    {m.role === 'user'
                      ? (m.image
                        ? <img src={m.image} alt="查询图" style={{ maxWidth: 220, maxHeight: 160, borderRadius: 8, display: 'block' }} />
                        : m.content)
                      : m.content
                        ? <MarkdownView content={m.content} />
                        : (m.streaming ? <span className="typing"><span /><span /><span /></span> : '')}
                  </div>
                  {m.role === 'bot' && m.imageResults && m.imageResults.length > 0 && (
                    <div className="img-grid">
                      {m.imageResults.map((h) => (
                        <div className="img-card" key={h.node_id}>
                          <AuthImage nodeId={h.node_id} alt={h.doc_name}
                            style={{ width: '100%', height: 120, objectFit: 'cover', borderRadius: 8 }} />
                          <div className="img-meta">
                            <span>{h.doc_name}</span>
                            {h.vector_score != null && <span className="score">{(h.vector_score * 100).toFixed(1)}%</span>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  {m.role === 'bot' && m.sources && m.sources.length > 0 && (
                    <div className="cites">
                      {m.sources.map((s) => (
                        <div className="cite" key={s.node_id}>
                          {s.modality === 'image' && (
                            <AuthImage nodeId={s.node_id} alt={s.doc_name}
                              style={{ width: 64, height: 46, objectFit: 'cover', borderRadius: 6 }} />
                          )}
                          <span>{s.doc_name}{s.page ? ` · p${s.page}` : ''}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="kb-scope">
            <KnowledgeScope kbs={kbs} value={selectedKbs} onChange={setSelectedKbs} />
            {selectedKbs.length > 0 && (
              <span className="muted">已限定 {selectedKbs.length} 个知识库</span>
            )}
          </div>

          <div className="chat-input">
            <input ref={imgRef} type="file" accept="image/*" style={{ display: 'none' }}
              onChange={(e) => { onPickImage(e.target.files?.[0]); e.currentTarget.value = '' }} />
            <button className="btn btn-o" title="上传图片以图搜图" aria-label="上传图片以图搜图"
              onClick={() => imgRef.current?.click()} disabled={busy || imgBusy} data-testid="chat-image">
              <ImageIcon size={16} />
            </button>
            <textarea className="input" value={input} placeholder="输入问题，Enter 发送 / Shift+Enter 换行；点左侧图片按钮以图搜图"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <button className="btn btn-p" onClick={send} disabled={busy} data-testid="chat-send"><Send size={15} /> 发送</button>
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <div className="card" style={{ maxHeight: 'calc(100vh - 200px)', overflow: 'auto' }}>
            <div className="card-head"><h3>会话</h3><span className="muted" style={{ marginLeft: 'auto' }}>{sessions.length}</span></div>
            <div className="card-pad" style={{ display: 'grid', gap: 4 }}>
              {sessions.map((s) => (
                <div key={s.session_id} className={`list-item ${s.session_id === sessionId ? 'active' : ''}`} onClick={() => switchSession(s.session_id)}>
                  <div className="row" style={{ gap: 6 }}>
                    <div className="t" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.title}</div>
                    <button className="btn btn-g btn-xs" aria-label="删除会话" onClick={(e) => removeSession(s.session_id, e)}><Trash2 size={12} /></button>
                  </div>
                  <div className="m"><span>{new Date(s.last * 1000).toLocaleString()}</span><span>{s.messages} 条</span></div>
                </div>
              ))}
              {sessions.length === 0 && <span className="muted">暂无历史会话</span>}
            </div>
          </div>
        </aside>
      </div>
    </>
  )
}
