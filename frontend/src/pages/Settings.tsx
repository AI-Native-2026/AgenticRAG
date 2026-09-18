import { useEffect, useState } from 'react'
import { api } from '@/api/client'
import { useTheme } from '@/store/theme'
import { toast } from '@/store/toast'

export default function Settings() {
  const { theme, set } = useTheme()
  const [connectors, setConnectors] = useState<Record<string, any>>({})
  const [ready, setReady] = useState<any>(null)

  useEffect(() => {
    api.get<any>('/v1/connectors').then((r) => setConnectors(r.connectors)).catch(() => {})
    fetch('/readyz').then((r) => r.json()).then(setReady).catch(() => {})
  }, [])

  return (
    <>
      <div className="page-head"><div><h1>设置</h1><div className="sub">连接器、服务状态与外观</div></div></div>

      <div className="grid g-2">
        <div className="card">
          <div className="card-head"><h3>支持的数据源类型</h3></div>
          <div className="card-pad">
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>类型</th><th>标识</th><th>能力</th></tr></thead>
              <tbody>
                {Object.entries(connectors).map(([k, v]: any) => (
                  <tr key={k}>
                    <td><span className="tag">{v.type}</span></td>
                    <td className="mono">{k}</td>
                    <td className="muted">{(v.capabilities || []).join(' · ')}</td>
                  </tr>
                ))}
                {Object.keys(connectors).length === 0 && <tr><td colSpan={3} className="muted">加载中…</td></tr>}
              </tbody>
            </table></div>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>服务状态</h3></div>
          <div className="card-pad">
            {ready ? (
              <>
                <div className="kv"><span className="k">就绪</span><span className="v">{ready.ready ? '✅ 是' : '⚠️ 否'}</span></div>
                {Object.entries(ready.checks || {}).map(([k, v]: any) => (
                  <div className="kv" key={k}><span className="k">{k}</span><span className="v">{v ? '正常' : '异常'}</span></div>
                ))}
              </>
            ) : <span className="muted">检测中…</span>}
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>外观</h3></div>
          <div className="card-pad">
            <div className="field"><label>主题</label>
              <div className="seg">
                <button className={theme === 'light' ? 'active' : ''} onClick={() => set('light')}>亮色</button>
                <button className={theme === 'dark' ? 'active' : ''} onClick={() => set('dark')}>暗色</button>
              </div>
            </div>
            <div className="note">主题偏好保存在本地</div>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3>检索与模型</h3></div>
          <div className="card-pad">
            <div className="kv"><span className="k">Embedding</span><span className="v">bge-small-zh-v1.5</span></div>
            <div className="kv"><span className="k">重排</span><span className="v">bge-reranker-base</span></div>
            <div className="kv"><span className="k">向量库</span><span className="v">ChromaDB</span></div>
            <div className="kv"><span className="k">队列</span><span className="v">Kafka / dev</span></div>
            <div className="note mt">通过后端 .env 配置，修改后需重启服务</div>
          </div>
        </div>
      </div>
    </>
  )
}
