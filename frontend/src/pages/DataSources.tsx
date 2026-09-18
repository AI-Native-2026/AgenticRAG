import { useEffect, useState } from 'react'
import { Plus, RefreshCw, Database, FileText, Globe, Play } from 'lucide-react'
import { api } from '@/api/client'
import { Drawer, Loading, Modal, Progress, StatusPill, Tabs, Empty } from '@/components/ui'
import { toast } from '@/store/toast'
import type { Datasource, Job, TableSchema } from '@/types'

const DB_TYPES = [
  { value: 'mysql', label: 'MySQL' },
  { value: 'postgresql', label: 'PostgreSQL' },
  { value: 'sqlite', label: 'SQLite' },
  { value: 'mssql', label: 'SQL Server' },
  { value: 'oracle', label: 'Oracle' },
  { value: 'mongodb', label: 'MongoDB' },
]

const typeIcon = (t: string) =>
  t === 'database' ? <Database size={15} /> : t === 'web' ? <Globe size={15} /> : <FileText size={15} />

const emptyForm = {
  name: '', type: 'file', subtype: 'directory',
  path: '', url: '', host: 'localhost', port: '', database: '',
  username: '', password: '',
}

export default function DataSources() {
  const [items, setItems] = useState<Datasource[] | null>(null)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ ...emptyForm })
  const [busy, setBusy] = useState(false)
  const [detail, setDetail] = useState<Datasource | null>(null)

  async function load() {
    try {
      const r = await api.get<{ datasources: Datasource[] }>('/v1/datasources')
      setItems(r.datasources)
    } catch (e: any) {
      toast.err(e.message)
    }
  }
  useEffect(() => { load() }, [])

  function buildPayload() {
    if (form.type === 'file') {
      return { name: form.name, type: 'file', subtype: 'directory', config: { path: form.path }, credentials: {} }
    }
    if (form.type === 'web') {
      return { name: form.name, type: 'web', subtype: 'web', config: { url: form.url }, credentials: {} }
    }
    const isMongo = form.subtype === 'mongodb'
    const config = isMongo
      ? { host: form.host, port: Number(form.port) || 27017, database: form.database }
      : { dialect: form.subtype, host: form.host, port: Number(form.port) || undefined, database: form.database }
    const credentials = form.username ? { username: form.username, password: form.password } : {}
    return { name: form.name, type: 'database', subtype: form.subtype, config, credentials }
  }

  async function create() {
    if (!form.name) return toast.err('请填写名称')
    setBusy(true)
    try {
      await api.post('/v1/datasources', buildPayload())
      toast.ok('数据源已创建')
      setOpen(false)
      setForm({ ...emptyForm })
      load()
    } catch (e: any) {
      toast.err(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function testConn() {
    setBusy(true)
    try {
      const p = buildPayload()
      const r = await api.post<{ ok: boolean; message: string }>('/v1/datasources/test', {
        subtype: p.subtype, config: p.config, credentials: p.credentials,
      })
      r.ok ? toast.ok(r.message) : toast.err(r.message)
    } catch (e: any) {
      toast.err(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function sync(ds: Datasource, mode: string) {
    try {
      const r = await api.post<{ job_id: string }>(`/v1/datasources/${ds.ds_id}/sync`, { mode })
      toast.ok(`已提交同步任务 ${r.job_id}`)
      setTimeout(load, 1500)
    } catch (e: any) {
      toast.err(e.message)
    }
  }

  return (
    <>
      <div className="page-head">
        <div><h1>数据源</h1><div className="sub">文件、数据库与 Web 统一接入管理</div></div>
        <div className="actions">
          <button className="btn btn-o" onClick={load}><RefreshCw size={15} /> 刷新</button>
          <button className="btn btn-p" onClick={() => setOpen(true)}><Plus size={15} /> 新建数据源</button>
        </div>
      </div>

      <div className="card">
        {!items ? (
          <div className="card-pad"><Loading rows={5} /></div>
        ) : items.length === 0 ? (
          <Empty title="还没有数据源" hint="点击右上角「新建数据源」接入文件或数据库" />
        ) : (
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>名称</th><th>类型</th><th>状态</th><th>Chunks</th><th>最近同步</th><th></th></tr></thead>
              <tbody>
                {items.map((d) => (
                  <tr key={d.ds_id} className="clickable" onClick={() => setDetail(d)}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
                        <span className="tag">{typeIcon(d.type)}</span>
                        <div><div style={{ fontWeight: 600 }}>{d.name}</div><div className="mono">{d.subtype}</div></div>
                      </div>
                    </td>
                    <td><span className="tag">{d.type}</span></td>
                    <td><StatusPill status={d.status} /></td>
                    <td className="mono">{d.chunk_count}</td>
                    <td className="muted">{d.last_sync_at ? new Date(d.last_sync_at * 1000).toLocaleString() : '—'}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <button className="btn btn-o btn-xs" onClick={() => sync(d, 'full')}><Play size={12} /> 同步</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <DatasourceDrawer ds={detail} onClose={() => setDetail(null)} onSynced={load} />

      <Modal
        open={open}
        title="新建数据源"
        onClose={() => setOpen(false)}
        width={560}
        footer={
          <>
            <button className="btn btn-o" onClick={() => setOpen(false)}>取消</button>
            <button className="btn btn-o" onClick={testConn} disabled={busy}>测试连接</button>
            <button className="btn btn-p" onClick={create} disabled={busy}>创建</button>
          </>
        }
      >
        <div className="field">
          <label htmlFor="ds-name">名称</label>
          <input id="ds-name" className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="如：订单库 / 产品文档目录" />
        </div>
        <div className="field">
          <label>类型</label>
          <div className="seg">
            {['file', 'database', 'web'].map((t) => (
              <button key={t} className={form.type === t ? 'active' : ''} onClick={() => setForm({ ...form, type: t })}>
                {t === 'file' ? '文件' : t === 'database' ? '数据库' : 'Web'}
              </button>
            ))}
          </div>
        </div>

        {form.type === 'file' && (
          <>
            <div className="field"><label htmlFor="ds-path">目录路径</label>
              <input id="ds-path" className="input" value={form.path} onChange={(e) => setForm({ ...form, path: e.target.value })} placeholder="/data/product-docs" /></div>
            <div className="note">支持 md/txt/pdf/docx/pptx/html/csv/xlsx/json</div>
          </>
        )}

        {form.type === 'web' && (
          <div className="field"><label htmlFor="ds-url">起始 URL</label>
            <input id="ds-url" className="input" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://docs.example.com" /></div>
        )}

        {form.type === 'database' && (
          <>
            <div className="field">
              <label htmlFor="ds-sub">数据库类型</label>
              <select id="ds-sub" className="select" value={form.subtype} onChange={(e) => setForm({ ...form, subtype: e.target.value })}>
                {DB_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
              </select>
            </div>
            {form.subtype === 'sqlite' ? (
              <div className="field"><label htmlFor="ds-file">SQLite 文件路径</label>
                <input id="ds-file" className="input" value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} placeholder="/data/app.db" /></div>
            ) : (
              <>
                <div className="row">
                  <div className="field" style={{ flex: 3 }}><label htmlFor="ds-host">主机</label>
                    <input id="ds-host" className="input" value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} /></div>
                  <div className="field" style={{ flex: 1 }}><label htmlFor="ds-port">端口</label>
                    <input id="ds-port" className="input" value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} /></div>
                </div>
                <div className="field"><label htmlFor="ds-db">数据库名</label>
                  <input id="ds-db" className="input" value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} /></div>
                <div className="row">
                  <div className="field" style={{ flex: 1 }}><label htmlFor="ds-user">只读账号</label>
                    <input id="ds-user" className="input" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} /></div>
                  <div className="field" style={{ flex: 1 }}><label htmlFor="ds-pass">密码</label>
                    <input id="ds-pass" className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></div>
                </div>
              </>
            )}
            <div className="note">凭证将加密存储；建议使用只读账号</div>
          </>
        )}
      </Modal>
    </>
  )
}

function DatasourceDrawer({ ds, onClose, onSynced }: { ds: Datasource | null; onClose: () => void; onSynced: () => void }) {
  const [tab, setTab] = useState('连接配置')
  const [tables, setTables] = useState<TableSchema[] | null>(null)
  const [preview, setPreview] = useState<any[] | null>(null)
  const [job, setJob] = useState<Job | null>(null)
  const [mode, setMode] = useState('full')
  const tabs = ds?.type === 'database' ? ['连接配置', 'Schema', '预览', '同步'] : ['连接配置', '预览', '同步']

  useEffect(() => {
    if (!ds) return
    setTab('连接配置'); setTables(null); setPreview(null); setJob(null)
  }, [ds])

  useEffect(() => {
    if (!ds) return
    if (tab === 'Schema') api.get<{ tables: TableSchema[] }>(`/v1/datasources/${ds.ds_id}/schema`).then((r) => setTables(r.tables)).catch(() => setTables([]))
    if (tab === '预览') api.get<{ preview: any[] }>(`/v1/datasources/${ds.ds_id}/preview?limit=10`).then((r) => setPreview(r.preview)).catch((e) => { toast.err(e.message); setPreview([]) })
  }, [tab, ds])

  async function runSync() {
    if (!ds) return
    try {
      const r = await api.post<{ job_id: string }>(`/v1/datasources/${ds.ds_id}/sync`, { mode })
      toast.ok('同步任务已提交')
      poll(r.job_id)
      onSynced()
    } catch (e: any) { toast.err(e.message) }
  }

  function poll(id: string) {
    const t = setInterval(async () => {
      try {
        const j = await api.get<Job>(`/v1/jobs/${id}`)
        setJob(j)
        if (j.status === 'success' || j.status === 'failed') { clearInterval(t); onSynced() }
      } catch { clearInterval(t) }
    }, 1500)
  }

  return (
    <Drawer open={!!ds} title={ds?.name || ''} onClose={onClose}
      footer={ds ? (
        <>
          <button className="btn btn-o" onClick={onClose}>关闭</button>
          <button className="btn btn-p" onClick={runSync}><Play size={14} /> 立即同步</button>
        </>
      ) : undefined}
    >
      {ds && (
        <>
          <div className="row mb">
            <span className="tag">{ds.type}</span>
            <span className="tag">{ds.subtype}</span>
            <StatusPill status={ds.status} />
            <span className="spacer" />
            <span className="muted">{ds.chunk_count} chunks</span>
          </div>
          <Tabs tabs={tabs} active={tab} onChange={setTab} />

          {tab === '连接配置' && (
            <>
              {Object.entries(ds.config || {}).map(([k, v]) => (
                <div className="kv" key={k}><span className="k">{k}</span><span className="v mono">{String(v)}</span></div>
              ))}
              <div className="kv"><span className="k">凭证</span><span className="v">{ds.has_credentials ? '已配置（加密）' : '无'}</span></div>
            </>
          )}

          {tab === 'Schema' && (
            !tables ? <Loading /> : tables.length === 0 ? <Empty title="暂无表结构" hint="同步后会自动抽取" /> : (
              <div className="tree">
                {tables.map((t) => (
                  <details key={t.table} open>
                    <summary className="node" style={{ cursor: 'pointer' }}>{t.table} <span className="muted">· {t.row_count} 行</span></summary>
                    <div className="children">
                      {t.columns.map((c) => (
                        <div className="col" key={c.name}>{c.name}<span className="ty">{c.type}{c.pk ? ' PK' : ''}</span></div>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            )
          )}

          {tab === '预览' && (
            !preview ? <Loading /> : preview.length === 0 ? <Empty title="暂无数据" /> : (
              <div style={{ display: 'grid', gap: 10 }}>
                {preview.map((p, i) => (
                  <div className="res" key={i}>
                    <div className="rh"><span className="rank">{i + 1}</span><span className="tag">{p.title}</span></div>
                    <div className="txt">{p.text}</div>
                  </div>
                ))}
              </div>
            )
          )}

          {tab === '同步' && (
            <>
              <div className="field">
                <label>同步模式</label>
                <div className="seg">
                  <button className={mode === 'full' ? 'active' : ''} onClick={() => setMode('full')}>全量</button>
                  <button className={mode === 'incremental' ? 'active' : ''} onClick={() => setMode('incremental')}>增量</button>
                </div>
              </div>
              {job && (
                <div className="card card-pad">
                  <div className="row mb"><StatusPill status={job.status} /><span className="spacer" /><span className="muted">{job.chunks} chunks · 失败 {job.failed}</span></div>
                  <Progress value={job.progress || 0} tone={job.status === 'failed' ? 'err' : undefined} />
                  {job.error && <pre className="code mt">{job.error}</pre>}
                </div>
              )}
              <div className="note mt">增量同步依赖水位线字段（数据源 config.watermark_column）</div>
            </>
          )}
        </>
      )}
    </Drawer>
  )
}
