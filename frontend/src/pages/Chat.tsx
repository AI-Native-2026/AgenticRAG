import { useRef, useState } from 'react'
import { Send } from 'lucide-react'
import { chatStream } from '@/api/client'
import { toast } from '@/store/toast'

interface ToolStep { tool: string; ok?: boolean; duration_ms?: number; detail?: string }
interface Message {
  role: 'user' | 'bot'
  content: string
  steps: ToolStep[]
  streaming?: boolean
}

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'bot', content: '你好，我是知识中台助手。可以帮你检索知识库，或查询已接入的数据库。', steps: [] },
  ])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const sessionId = useRef(`web-${Date.now()}`)
  const scrollRef = useRef<HTMLDivElement>(null)

  function scrollDown() {
    requestAnimationFrame(() => { if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight })
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
      await chatStream(q, sessionId.current, (event, data) => {
        if (event === 'token') {
          updateBot((msg) => ({ ...msg, content: msg.content + (data.content || '') }))
          scrollDown()
        } else if (event === 'retrieval') {
          updateBot((msg) => ({ ...msg, steps: [...msg.steps, { tool: 'kb_search', detail: `召回 ${data.n_candidates} 条 · ${data.duration_ms}ms` }] }))
        } else if (event === 'rerank') {
          updateBot((msg) => ({ ...msg, steps: [...msg.steps, { tool: 'rerank', detail: `重排 ${data.n_output} 条 · ${data.duration_ms}ms` }] }))
        } else if (event === 'sql') {
          updateBot((msg) => ({ ...msg, steps: [...msg.steps, { tool: 'sql_query', detail: `${data.row_count} 行`, }] }))
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
      })
    } catch (e: any) {
      toast.err(e.message)
    } finally {
      updateBot((msg) => ({ ...msg, streaming: false }))
      setBusy(false)
      scrollDown()
    }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>Agent 对话</h1><div className="sub">多轮对话 · 工具调用 · 引用溯源</div></div>
        <div className="actions"><button className="btn btn-o" onClick={() => { sessionId.current = `web-${Date.now()}`; setMessages([{ role: 'bot', content: '已开启新会话。', steps: [] }]) }}>新建会话</button></div>
      </div>

      <div className="chat-wrap">
        <div className="card chat-main">
          <div className="chat-scroll" ref={scrollRef}>
            {messages.map((m, i) => (
              <div key={i} className={`msg ${m.role}`}>
                <div className="av">{m.role === 'user' ? 'A' : 'K'}</div>
                <div>
                  <div className="bub">
                    {m.content || (m.streaming ? <span className="typing"><span /><span /><span /></span> : '')}
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
          <div className="card card-pad">
            <div style={{ fontWeight: 600, marginBottom: 9 }}>检索范围</div>
            <div className="muted">以登录租户 <b>{''}</b> 为准，自动隔离</div>
            <div className="note mt">可在「知识库」页配置数据源分组</div>
          </div>
        </aside>
      </div>
    </>
  )
}
