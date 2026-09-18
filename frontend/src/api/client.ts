const TOKEN_KEY = 'kr_token'
const USER_KEY = 'kr_user'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t)
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}
export function setUser(u: unknown) {
  localStorage.setItem(USER_KEY, JSON.stringify(u))
}
export function getUser<T>(): T | null {
  const raw = localStorage.getItem(USER_KEY)
  return raw ? (JSON.parse(raw) as T) : null
}

export class ApiError extends Error {
  code: string
  status: number
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function parseError(res: Response): Promise<never> {
  let code = 'ERROR'
  let message = `HTTP ${res.status}`
  try {
    const body = await res.json()
    code = body.code || code
    message = body.message || message
  } catch {
    /* ignore */
  }
  if (res.status === 401) {
    clearToken()
    window.dispatchEvent(new Event('kr:unauthorized'))
  }
  throw new ApiError(res.status, code, message)
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(path, { ...options, headers })
  if (!res.ok) return parseError(res)
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

export const api = {
  get: <T>(p: string) => request<T>(p),
  post: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T>(p: string, body?: unknown) =>
    request<T>(p, { method: 'PATCH', body: JSON.stringify(body) }),
  del: <T>(p: string) => request<T>(p, { method: 'DELETE' }),
}

/** 流式对话：逐步骤回调。 */
export async function chatStream(
  question: string,
  sessionId: string,
  onStep: (event: string, data: any) => void,
  opts: { kbIds?: string[]; signal?: AbortSignal } = {},
): Promise<void> {
  const res = await fetch('/v1/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({
      question, session_id: sessionId, stream: true,
      kb_ids: opts.kbIds || [],
    }),
    signal: opts.signal,
  })
  if (!res.ok || !res.body) return parseError(res)

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const chunks = buffer.split('\n\n')
    buffer = chunks.pop() || ''
    for (const chunk of chunks) {
      let event = 'message'
      let data = ''
      for (const line of chunk.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data += line.slice(5).trim()
      }
      if (data) {
        try {
          onStep(event, JSON.parse(data))
        } catch {
          onStep(event, { raw: data })
        }
      }
    }
  }
}
