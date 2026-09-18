import { useEffect } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import AppShell from '@/layouts/AppShell'
import { useAuth } from '@/store/auth'
import Login from '@/pages/Login'
import Dashboard from '@/pages/Dashboard'
import KnowledgeBases from '@/pages/KnowledgeBases'
import DataSources from '@/pages/DataSources'
import Jobs from '@/pages/Jobs'
import Documents from '@/pages/Documents'
import Retrieval from '@/pages/Retrieval'
import Chat from '@/pages/Chat'
import Eval from '@/pages/Eval'
import Observability from '@/pages/Observability'
import Tenants from '@/pages/Tenants'
import Settings from '@/pages/Settings'

function Protected({ children }: { children: React.ReactNode }) {
  const token = useAuth((s) => s.token)
  const logout = useAuth((s) => s.logout)
  const nav = useNavigate()

  useEffect(() => {
    const handler = () => { logout(); nav('/login') }
    window.addEventListener('kr:unauthorized', handler)
    return () => window.removeEventListener('kr:unauthorized', handler)
  }, [logout, nav])

  if (!token) return <Navigate to="/login" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Protected><AppShell /></Protected>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="knowledge-bases" element={<KnowledgeBases />} />
          <Route path="datasources" element={<DataSources />} />
          <Route path="jobs" element={<Jobs />} />
          <Route path="documents" element={<Documents />} />
          <Route path="retrieval" element={<Retrieval />} />
          <Route path="chat" element={<Chat />} />
          <Route path="eval" element={<Eval />} />
          <Route path="observability" element={<Observability />} />
          <Route path="tenants" element={<Tenants />} />
          <Route path="settings" element={<Settings />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
