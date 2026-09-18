import { create } from 'zustand'

type Theme = 'light' | 'dark'

interface ThemeState {
  theme: Theme
  toggle: () => void
  set: (t: Theme) => void
}

const saved = (localStorage.getItem('kr-theme') as Theme) || 'light'
document.documentElement.dataset.theme = saved

export const useTheme = create<ThemeState>((set, get) => ({
  theme: saved,
  toggle: () => get().set(get().theme === 'dark' ? 'light' : 'dark'),
  set: (t) => {
    localStorage.setItem('kr-theme', t)
    document.documentElement.dataset.theme = t
    set({ theme: t })
  },
}))
