import { useEffect, useState } from 'react'
import { RefreshCw, RotateCcw } from 'lucide-react'
import { api } from '@/api/client'
import { Drawer, Empty, Loading, Progress, StatusPill } from '@/components/ui'
import { toast } from '@/store/toast'
import type { Job } from '@/types'

export default function Jobs() {
  const [items, setItems] = useState<Job[] | null>(null)
  const [filter, setFilter] = useState('all')
  const [detail, setDetail] = useState<Job | null>(null)

  async function load() {
    try {
      const r = await api.get<{ jobs: Job[] }>('/v1/jobs')
      setItems(r.jobs)
    } catch (e: any) { toast.err(e.message) }
  }
  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [])

  async function retry(job: Job) {
    try {
      await api.post(`/v1/jobs/${job.job_id}/retry`)
      toast.ok('已重新提交')
      load()
    } catch (e: any) { toast.err(e.message) }
  }

  const shown = (items || []).filter((j) => filter === 'all' || j.status === filter)

  return (
    <>
      <div className="page-head">
        <div><h1>入库任务</h1><div className="sub">解析、切分、向量化与同步任务</div></div>
        <div className="actions"><button className="btn btn-o" onClick={load}><RefreshCw size={15} /> 刷新</button></div>
      </div>

      <div className="row wrap mb">
        <div className="seg">
          {['all', 'running', 'success', 'failed'].map((f) => (
            <button key={f} className={filter === f ? 'active' : ''} onClick={() => setFilter(f)}>
              {f === 'all' ? '全部' : f === 'running' ? '运行中' : f === 'success' ? '成功' : '失败'}
            </button>
          ))}
        </div>
        <span className="spacer" />
        <span className="muted">共 {shown.length} 条</span>
      </div>

      <div className="card">
        {!items ? <div className="card-pad"><Loading rows={5} /></div> :
          shown.length === 0 ? <Empty title="暂无任务" /> : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>任务</th><th>数据源</th><th>模式</th><th>进度 / 结果</th><th>状态</th><th></th></tr></thead>
                <tbody>
                  {shown.map((j) => (
                    <tr key={j.job_id} className="clickable" onClick={() => setDetail(j)}>
                      <td className="mono">{j.job_id}</td>
                      <td className="mono">{j.datasource_id}</td>
                      <td><span className="tag">{j.mode}</span></td>
                      <td style={{ minWidth: 180 }}>
                        {j.status === 'running' || j.status === 'pending'
                          ? <div className="bar-row"><Progress value={j.progress || 0} /><span>{j.progress || 0}%</span></div>
                          : <span className="mono">{j.chunks} chunks · 跳过 {j.skipped} · 失败 {j.failed}</span>}
                      </td>
                      <td><StatusPill status={j.status} /></td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {j.status === 'failed' && <button className="btn btn-o btn-xs" onClick={() => retry(j)}><RotateCcw size={12} /> 重试</button>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>

      <Drawer open={!!detail} title={detail?.job_id || ''} onClose={() => setDetail(null)}>
        {detail && (
          <>
            <div className="row mb"><StatusPill status={detail.status} /><span className="spacer" /><span className="muted">{detail.mode}</span></div>
            <div className="kv"><span className="k">数据源</span><span className="v mono">{detail.datasource_id}</span></div>
            <div className="kv"><span className="k">处理</span><span className="v">{detail.processed} / {detail.total || '—'}</span></div>
            <div className="kv"><span className="k">Chunks</span><span className="v">{detail.chunks}</span></div>
            <div className="kv"><span className="k">跳过 / 失败</span><span className="v">{detail.skipped} / {detail.failed}</span></div>
            <div className="kv"><span className="k">开始</span><span className="v">{detail.started_at ? new Date(detail.started_at * 1000).toLocaleString() : '—'}</span></div>
            <div className="kv"><span className="k">结束</span><span className="v">{detail.finished_at ? new Date(detail.finished_at * 1000).toLocaleString() : '—'}</span></div>
            {detail.error && <><div className="divider" /><div className="muted mb">错误</div><pre className="code">{detail.error}</pre></>}
          </>
        )}
      </Drawer>
    </>
  )
}
