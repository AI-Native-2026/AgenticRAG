import { NavLink, Outlet, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Layers, Database, Inbox, FileText, Search, MessageSquare,
  ClipboardCheck, Activity, Users, Settings, Moon, Sun, Menu, LogOut, Bell,
} from 'lucide-react'
import { useAuth } from '@/store/auth'
import { useTheme } from '@/store/theme'
import { ToastHost } from '@/components/ui'

const NAV: { group: string; items: { to: string; label: string; icon: any }[] }[] = [
  { group: '总览', items: [{ to: '/dashboard', label: '概览', icon: LayoutDashboard }] },
  {
    group: '数据',
    items: [
      { to: '/knowledge-bases', label: '知识库', icon: Layers },
      { to: '/datasources', label: '数据源', icon: Database },
      { to: '/jobs', label: '入库任务', icon: Inbox },
      { to: '/documents', label: '文档浏览', icon: FileText },
    ],
  },
  {
    group: '应用',
    items: [
      { to: '/retrieval', label: '检索调试台', icon: Search },
      { to: '/chat', label: 'Agent 对话', icon: MessageSquare },
      { to: '/eval', label: '评测', icon: ClipboardCheck },
    ],
  },
  {
    group: '运维',
    items: [
      { to: '/observability', label: '观测', icon: Activity },
      { to: '/tenants', label: '租户与配额', icon: Users },
      { to: '/settings', label: '设置', icon: Settings },
    ],
  },
]

const TITLES: Record<string, string> = Object.fromEntries(
  NAV.flatMap((g) => g.items.map((i) => [i.to, i.label])),
)

export default function AppShell() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const location = useLocation()
  const crumb = TITLES[location.pathname] || (location.pathname.startsWith('/datasources') ? '数据源详情' : '概览')

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="logo">
          <div className="mark">K</div>
          <div>
            <div className="nm">知识中台</div>
            <div className="sub">Agentic RAG</div>
          </div>
        </div>
        <nav className="nav" aria-label="主导航">
          {NAV.map((g) => (
            <div key={g.group}>
              <div className="grp">{g.group}</div>
              {g.items.map((it) => (
                <NavLink key={it.to} to={it.to} className={({ isActive }) => (isActive ? 'active' : '')}>
                  <it.icon size={17} />
                  <span>{it.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <span className="pulse" /> 服务正常
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <button className="btn btn-g btn-sm" aria-label="切换菜单" onClick={() => document.querySelector('.sidebar')?.classList.toggle('open')}>
            <Menu size={16} />
          </button>
          <div className="crumb">
            <span>知识中台</span>
            <span>/</span>
            <b>{crumb}</b>
          </div>
          <button className="search-trigger" aria-label="全局搜索">
            <Search size={15} />
            <span>搜索…</span>
            <kbd>⌘K</kbd>
          </button>
          <div className="top-actions">
            <button className="btn btn-g btn-sm" aria-label="通知"><Bell size={16} /></button>
            <button className="btn btn-g btn-sm" aria-label="切换主题" onClick={toggle}>
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <span className="tag">{user?.tenant} · {user?.role}</span>
            <button className="btn btn-o btn-sm" onClick={logout} aria-label="退出登录">
              <LogOut size={14} /> 退出
            </button>
          </div>
        </header>

        <main className="content rise">
          <Outlet />
        </main>
      </div>
      <ToastHost />
    </div>
  )
}
