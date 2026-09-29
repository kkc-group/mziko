import type { AnswerResult, LockStatus, LoginOut, Me, SessionOut, SessionSummary } from './types'

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
  /** The `detail` of the error body: a string, or an object for login errors. */
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : JSON.stringify(detail))
    this.status = status
    this.detail = detail
  }
}

// A hung request (dead wifi, sleeping backend) should fail like an offline one
// instead of leaving the caller's busy state stuck forever.
const REQUEST_TIMEOUT_MS = 15_000

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  try {
    const response = await fetch(path, { ...init, headers, signal: controller.signal })
    if (!response.ok) {
      let detail: unknown = response.statusText
      try {
        detail = (await response.json()).detail ?? detail
      } catch {
        /* non-JSON error body */
      }
      throw new ApiError(response.status, detail)
    }
    return (await response.json()) as T
  } finally {
    clearTimeout(timeout)
  }
}

export interface AnswerBody {
  step_index: number
  word_slug: string
  attempt: number
  client_answer_id: string
}

export const api = {
  /** 401 → detail {error:'wrong_code', attempts_left}; 423 → detail {error:'locked', locked_until}. */
  login: (word: string, pin: string, deviceName: string) =>
    request<LoginOut>('/api/login', {
      method: 'POST',
      body: JSON.stringify({ word, pin, device_name: deviceName }),
    }),
  /** Lock state of this device's address; polled by the lock screen. */
  loginStatus: () => request<LockStatus>('/api/login/status'),
  me: () => request<Me>('/api/me'),
  startSession: (lesson: number | null) =>
    request<SessionOut>('/api/sessions', { method: 'POST', body: JSON.stringify({ lesson }) }),
  /** Start the topic over from its first lesson; 409 when the topic is locked today. */
  restartTopic: (slug: string) =>
    request<SessionOut>(`/api/topics/${encodeURIComponent(slug)}/restart`, { method: 'POST' }),
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
