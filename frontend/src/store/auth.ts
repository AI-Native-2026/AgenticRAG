import { create } from 'zustand'
import { api, clearToken, getToken, getUser, setToken, setUser } from '@/api/client'
import type { LoginResponse, User } from '@/types'

interface AuthState {
  user: User | null
  token: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  isAuthed: () => boolean
}

export const useAuth = create<AuthState>((set, get) => ({
  user: getUser<User>(),
  token: getToken(),
  login: async (username, password) => {
    const res = await api.post<LoginResponse>('/v1/auth/login', { username, password })
    setToken(res.access_token)
    setUser(res.user)
    set({ token: res.access_token, user: res.user })
  },
  logout: () => {
    clearToken()
    set({ token: null, user: null })
  },
  isAuthed: () => Boolean(get().token),
}))
