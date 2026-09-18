import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '@/store/auth'
import { toast, useToast } from '@/store/toast'
import { ToastHost } from '@/components/ui'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('admin123')
  const [loading, setLoading] = useState(false)
  const push = useToast((s) => s.push)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    try {
      await login(username, password)
      push('ok', '登录成功')
      nav('/dashboard')
    } catch (err: any) {
      push('err', err?.message || '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-brand">
        <div>
          <div className="b-mark">K</div>
          <h1>Agentic RAG<br />企业知识中台</h1>
          <p className="lede">统一接入文件与数据库，构建可检索、可溯源、可编排的智能知识底座。</p>
          <ul>
            <li>多格式文件 + 多类型数据库统一接入</li>
            <li>混合检索 · 重排 · 引用溯源</li>
            <li>Agent 编排 · 工具治理 · 全链路观测</li>
          </ul>
        </div>
        <div className="foot">© 2026 Agentic RAG Platform</div>
      </div>
      <div className="login-form">
        <form className="login-card" onSubmit={submit}>
          <h2>登录控制台</h2>
          <div className="sub">使用租户账号登录知识中台</div>
          <div className="field">
            <label htmlFor="u">账号</label>
            <input id="u" className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
          </div>
          <div className="field">
            <label htmlFor="p">密码</label>
            <input id="p" className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
          </div>
          <button className="btn btn-p" style={{ width: '100%' }} disabled={loading} data-testid="login-submit">
            {loading ? '登录中…' : '登录'}
          </button>
          <p className="muted mt" style={{ textAlign: 'center' }}>演示账号 admin / admin123 · 租户 tech</p>
        </form>
      </div>
      <ToastHost />
    </div>
  )
}
