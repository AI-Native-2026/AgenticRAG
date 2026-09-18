import { create } from 'zustand'

export type ToastKind = 'ok' | 'err' | 'info'

export interface ToastItem {
  id: number
  kind: ToastKind
  message: string
}

interface ToastState {
  toasts: ToastItem[]
  push: (kind: ToastKind, message: string) => void
  remove: (id: number) => void
}

let seq = 1

export const useToast = create<ToastState>((set, get) => ({
  toasts: [],
  push: (kind, message) => {
    const id = seq++
    set({ toasts: [...get().toasts, { id, kind, message }] })
    setTimeout(() => get().remove(id), 3200)
  },
  remove: (id) => set({ toasts: get().toasts.filter((t) => t.id !== id) }),
}))

export const toast = {
  ok: (m: string) => useToast.getState().push('ok', m),
  err: (m: string) => useToast.getState().push('err', m),
  info: (m: string) => useToast.getState().push('info', m),
}
