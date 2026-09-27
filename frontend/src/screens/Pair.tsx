import { useEffect, useState } from 'react'
import { api, ApiError, setToken } from '../api'
import { Mascot } from '../components/Mascot'

function deviceName(): string {
  const ua = navigator.userAgent
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'iPad'
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/Android/.test(ua)) return 'Android'
  return 'Браузер'
}

// A pairing code is single-use, so concurrent callers (React StrictMode runs
// effects twice in development) must share one request.
const inFlight = new Map<string, ReturnType<typeof api.pair>>()
function pairOnce(code: string) {
  let p = inFlight.get(code)
  if (!p) {
    p = api.pair(code, deviceName())
    inFlight.set(code, p)
  }
  return p
}

export function Pair({ code, onPaired }: { code: string; onPaired: () => void }) {
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    pairOnce(code)
      .then((r) => {
        if (cancelled) return
        setToken(r.device_token)
        history.replaceState(null, '', '/')
        onPaired()
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setError(
          e instanceof ApiError && e.status === 404
            ? 'Ссылка недействительна или устарела. Попросите новую в боте командой /pair.'
            : 'Не получилось связаться с сервером. Проверьте интернет и откройте ссылку ещё раз.',
        )
      })
    return () => {
      cancelled = true
    }
  }, [code, onPaired])

  return (
    <main className="wrap center">
      <Mascot />
      <div className="card">
        {error ? (
          <>
            <h2>Не вышло</h2>
            <p className="muted">{error}</p>
          </>
        ) : (
          <>
            <h2>Привязываю устройство…</h2>
            <p className="muted">Секундочку</p>
          </>
        )}
      </div>
    </main>
  )
}

export function Unpaired() {
  return (
    <main className="wrap center">
      <Mascot />
      <div className="card">
        <span className="ka big">გამარჯობა!</span>
        <h2>Это устройство ещё не привязано</h2>
        <p className="muted">
          Попросите родителя отправить боту команду <b>/pair</b> и откройте полученную ссылку здесь.
        </p>
      </div>
    </main>
  )
}
