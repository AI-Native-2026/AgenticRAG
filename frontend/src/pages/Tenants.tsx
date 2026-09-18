import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '@/api/client'
import { Empty, Loading, Modal, Progress } from '@/components/ui'
import { toast } from '@/store/toast'
import { useAuth } from '@/store/auth'

export default function Tenants() {
  const user = useAuth((s) => s.user)
  const [items, setItems] = useState<any[] | null>(null)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ tenant: '', quota_tokens_per_day: 100000, quota_storage_nodes: 10000 })

  async function load() {
    try {
      const r = await api.get<{ tenants: any[] }>('/v1/tenants')
      setItems(r.tenants)
    } catch (e: any) { toast.err(e.message); setItems([]) }
  }
  useEffect(() => { load() }, [])

  async function create() {
    try {
      await api.post('/v1/tenants', form)
      toast.ok('租户已创建')
      setOpen(false); load()
    } catch (e: any) { toast.err(e.message) }
  }

  const isAdmin = user?.role === 'admin'

  return (
    <>
      <div className="page-head">
        <div><h1>租户与配额</h1><div className="sub">多租户隔离、Token 与存储配额</div></div>
        {isAdmin && <div className="actions"><button className="btn btn-p" onClick={() => setOpen(true)}><Plus size={15} /> 新建租户</button></div>}
      </div>

      <div className="card">
        {!items ? <div className="card-pad"><Loading rows={3} /></div> :
          items.length === 0 ? <Empty title="无权查看或暂无租户" hint="仅管理员可管理租户" /> : (
            <div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>租户</th><th>Token 配额（今日）</th><th>存储配额</th><th>创建时间</th></tr></thead>
              <tbody>{items.map((t) => {
                const tokenPct = Math.min(100, ((t.used_tokens_today || 0) / (t.quota_tokens_per_day || 1)) * 100)
                const storePct = Math.min(100, ((t.stored_nodes || 0) / (t.quota_storage_nodes || 1)) * 100)
                return (
                  <tr key={t._id}>
                    <td style={{ fontWeight: 600 }}>{t._id}</td>
                    <td style={{ minWidth: 200 }}>
                      <div className="bar-row">
                        <Progress value={tokenPct} tone={tokenPct > 90 ? 'err' : tokenPct > 70 ? 'warn' : undefined} />
                        <span className="mono">{t.used_tokens_today || 0}/{t.quota_tokens_per_day}</span>
                      </div>
                    </td>
                    <td style={{ minWidth: 200 }}>
                      <div className="bar-row">
                        <Progress value={storePct} tone={storePct > 90 ? 'err' : 'ok'} />
                        <span className="mono">{t.stored_nodes || 0}/{t.quota_storage_nodes}</span>
                      </div>
                    </td>
                    <td className="muted">{t.created_at ? new Date(t.created_at * 1000).toLocaleDateString() : '—'}</td>
                  </tr>
                )
              })}</tbody>
            </table></div>
          )}
      </div>

      <Modal open={open} title="新建租户" onClose={() => setOpen(false)}
        footer={<><button className="btn btn-o" onClick={() => setOpen(false)}>取消</button><button className="btn btn-p" onClick={create}>创建</button></>}>
        <div className="field"><label htmlFor="t-id">租户标识</label>
          <input id="t-id" className="input" value={form.tenant} onChange={(e) => setForm({ ...form, tenant: e.target.value })} placeholder="如：finance" /></div>
        <div className="field"><label htmlFor="t-tok">日 Token 配额</label>
          <input id="t-tok" className="input" type="number" value={form.quota_tokens_per_day} onChange={(e) => setForm({ ...form, quota_tokens_per_day: Number(e.target.value) })} /></div>
        <div className="field"><label htmlFor="t-st">存储节点配额</label>
          <input id="t-st" className="input" type="number" value={form.quota_storage_nodes} onChange={(e) => setForm({ ...form, quota_storage_nodes: Number(e.target.value) })} /></div>
      </Modal>
    </>
  )
}
