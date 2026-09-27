import type { AnswerResult, Me, SessionOut, SessionSummary } from './types'

const TOKEN_KEY = 'mziko-device-token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode: the session simply will not survive a reload */
  }
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const response = await fetch(path, { ...init, headers })
  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export interface AnswerBody {
  step_index: number
  word_slug: string
  attempt: number
  client_answer_id: string
}

export const api = {
  pair: (code: string, deviceName: string) =>
    request<{ device_token: string; child: { id: number; name: string } }>(
      `/api/pair/${encodeURIComponent(code)}`,
      { method: 'POST', body: JSON.stringify({ device_name: deviceName }) },
    ),
  me: () => request<Me>('/api/me'),
  startSession: (topic_slug: string) =>
    request<SessionOut>('/api/sessions', { method: 'POST', body: JSON.stringify({ topic_slug }) }),
  answer: (sessionId: string, body: AnswerBody) =>
    request<AnswerResult>(`/api/sessions/${sessionId}/answers`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  finish: (sessionId: string) =>
    request<SessionSummary>(`/api/sessions/${sessionId}/finish`, { method: 'POST' }),
}

/** Retry a request on network failure (not on HTTP errors). Same payload every time. */
export async function withRetry<T>(fn: () => Promise<T>, attempts = 4): Promise<T> {
  let delay = 700
  for (let i = 1; ; i++) {
    try {
      return await fn()
    } catch (error) {
      if (error instanceof ApiError || i >= attempts) throw error
      await new Promise((r) => setTimeout(r, delay))
      delay = Math.min(delay * 2, 4000)
    }
  }
}
