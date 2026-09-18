import { useEffect, useRef, useState } from 'react'
import { Plus, Send, Trash2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, chatStream } from '@/api/client'
import { toast } from '@/store/toast'

interface ToolStep { tool: string; ok?: boolean; duration_ms?: number; detail?: string }
interface Message { role: 'user' | 'bot'; content: string; steps: ToolStep[]; streaming?: boolean }
interface SessionMeta { session_id: string; title: string; last: number; messages: number }

const SESSION_KEY = 'kr_session'

function newSessionId() {
  return `web-${Date.now().toString(36)}`
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: '你好，我是 **小K**，你的知识中台助手。可以帮你检索知识库，或查询已接入的数据库。', steps: [] },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem(SESSION_KEY) || newSessionId())
  const [sessions, setSessions] = useState<SessionMeta[]>([])
  const [memory, setMemory] = useState<any>(null)
  const [kbs, setKbs] = useState<any[]>([])
  const [selectedKbs, setSelectedKbs] = useState<string[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)

  function scrollDown() {
    requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight })
  }

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

  useEffect(() => {
    api.get<any>(`/v1/sessions/${sessionId}/memory`).then(setMemory).catch(() => setMemory(null))
  }, [sessionId, messages.length])

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

    const updateBot = (fn: (msg: Message) => Message) =>
      setMessages((m) => m.map((msg, i) => (i === m.length - 1 ? fn(msg) : msg)))

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

  return (
    <>
      <div className="page-head">
        <div><h1>Agent 对话</h1><div className="sub">多轮对话 · 工具调用 · 引用溯源（会话已持久化）</div></div>
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
                      ? m.content
                      : m.content
                        ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                        : (m.streaming ? <span className="typing"><span /><span /><span /></span> : '')}
                  </div>
                  {m.steps.map((s, j) => (
                    <div className="tool-call" key={j}>
                      <div className="tc-head">{s.tool}{s.ok === false ? ' · 失败' : s.ok ? ' · 成功' : ''}{s.detail ? ` · ${s.detail}` : ''}</div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="chat-input">
            <textarea className="input" value={input} placeholder="输入问题，Enter 发送 / Shift+Enter 换行"
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }} />
            <button className="btn btn-p" onClick={send} disabled={busy} data-testid="chat-send"><Send size={15} /> 发送</button>
          </div>
        </div>

        <aside style={{ display: 'grid', gap: 16, alignContent: 'start' }}>
          <div className="card" style={{ maxHeight: 420, overflow: 'auto' }}>
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
          <div className="card card-pad">
            <div className="row" style={{ marginBottom: 9 }}>
              <div style={{ fontWeight: 600 }}>检索范围（知识库）</div>
              <span className="spacer" />
              <button className="btn btn-g btn-xs" onClick={() => setSelectedKbs([])}>全部</button>
            </div>
            {kbs.length === 0 ? <span className="muted">暂无知识库</span> : (
              <div style={{ display: 'grid', gap: 8 }}>
                {kbs.map((k) => (
                  <label key={k.kb_id} className="row" style={{ gap: 8 }}>
                    <input type="checkbox" checked={selectedKbs.includes(k.kb_id)}
                      onChange={(e) => setSelectedKbs(e.target.checked
                        ? [...selectedKbs, k.kb_id]
                        : selectedKbs.filter((x) => x !== k.kb_id))} />
                    <span>{k.name}</span>
                    <span className="spacer" />
                    <span className="muted">{k.datasource_count ?? k.datasource_ids?.length ?? 0} 源</span>
                  </label>
                ))}
              </div>
            )}
            <div className="muted mt">{selectedKbs.length === 0 ? '当前：全部知识库' : `已选 ${selectedKbs.length} 个知识库`}</div>
          </div>
          <div className="card card-pad">
            <div style={{ fontWeight: 600, marginBottom: 9 }}>记忆与上下文</div>
            {memory ? (
              <>
                <div className="kv"><span className="k">消息数</span><span className="v">{memory.messages}</span></div>
                <div className="kv"><span className="k">已压缩</span><span className="v">{memory.summarized} 条</span></div>
                <div className="kv"><span className="k">长期摘要</span><span className="v">{memory.has_summary ? '已生成' : '无'}</span></div>
                <div className="kv"><span className="k">短期预算</span><span className="v">{memory.token_limit} tokens</span></div>
                {memory.summary && (
                  <details className="mt">
                    <summary className="muted" style={{ cursor: 'pointer' }}>查看摘要</summary>
                    <div className="muted mt" style={{ lineHeight: 1.6 }}>{memory.summary}</div>
                  </details>
                )}
              </>
            ) : <span className="muted">加载中…</span>}
          </div>
        </aside>
      </div>
    </>
  )
}
