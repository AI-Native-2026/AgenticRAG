import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { api } from '@/api/client'
import { Donut, Empty, Loading, Modal } from '@/components/ui'
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
    if (!form.tenant) return toast.err('请填写租户标识')
    try {
      await api.post('/v1/tenants', form)
      toast.ok('租户已创建')
      setOpen(false); setForm({ tenant: '', quota_tokens_per_day: 100000, quota_storage_nodes: 10000 }); load()
    } catch (e: any) { toast.err(e.message) }
  }

  const isAdmin = user?.role === 'admin'
  const usedColor = (pct: number) => (pct > 90 ? 'var(--red)' : pct > 70 ? 'var(--amber)' : 'var(--accent)')

  return (
    <>
      <div className="page-head">
        <div><h1>租户与配额</h1><div className="sub">多租户隔离、Token 与存储配额</div></div>
        {isAdmin && <div className="actions"><button className="btn btn-p" onClick={() => setOpen(true)}><Plus size={15} /> 新建租户</button></div>}
      </div>

      {!items ? <div className="card card-pad"><Loading rows={3} /></div> :
        items.length === 0 ? <div className="card"><Empty title="无权查看或暂无租户" hint="仅管理员可管理租户" /></div> : (
          <div className="grid g-3">
            {items.map((t) => {
              const tokenUsed = t.used_tokens_today || 0
              const tokenLimit = t.quota_tokens_per_day || 1
              const tokenPct = Math.min(100, (tokenUsed / tokenLimit) * 100)
              const storeUsed = t.stored_nodes || 0
              const storeLimit = t.quota_storage_nodes || 1
              const storePct = Math.min(100, (storeUsed / storeLimit) * 100)
              return (
                <div className="card card-pad" key={t._id}>
                  <div className="row" style={{ marginBottom: 14 }}>
                    <span style={{ width: 34, height: 34, borderRadius: 10, background: 'linear-gradient(135deg,var(--accent),var(--accent-2))', color: '#fff', display: 'grid', placeItems: 'center', fontWeight: 700 }}>
                      {String(t._id).slice(0, 1).toUpperCase()}
                    </span>
                    <div>
                      <div style={{ fontWeight: 700 }}>{t._id}</div>
                      <div className="muted">{t.created_at ? new Date(t.created_at * 1000).toLocaleDateString() : '—'}</div>
                    </div>
                    <span className="spacer" />
                    <span className={`pill ${tokenPct > 90 ? 'err' : tokenPct > 70 ? 'warn' : 'ok'}`}>
                      {tokenPct > 90 ? '超配额' : '正常'}
                    </span>
                  </div>

                  <div className="row" style={{ justifyContent: 'space-around' }}>
                    <div style={{ textAlign: 'center' }}>
                      <Donut
                        size={124}
                        thickness={12}
                        segments={[
                          { value: tokenUsed, color: usedColor(tokenPct) },
                          { value: Math.max(0, tokenLimit - tokenUsed), color: 'transparent' },
                        ]}
                        centerValue={`${tokenPct.toFixed(0)}%`}
                        centerLabel="Token"
                      />
                      <div className="muted" style={{ marginTop: 6 }}>
                        {tokenUsed.toLocaleString()} / {tokenLimit.toLocaleString()}
                      </div>
                    </div>
                    <div style={{ textAlign: 'center' }}>
                      <Donut
                        size={124}
                        thickness={12}
                        segments={[
                          { value: storeUsed, color: usedColor(storePct) },
                          { value: Math.max(0, storeLimit - storeUsed), color: 'transparent' },
                        ]}
                        centerValue={`${storePct.toFixed(0)}%`}
                        centerLabel="存储"
                      />
                      <div className="muted" style={{ marginTop: 6 }}>
                        {storeUsed.toLocaleString()} / {storeLimit.toLocaleString()}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}

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
