import { useEffect, useMemo, useState } from 'react'
import { api, ApiError, setToken } from '../api'
import { Mascot } from '../components/Mascot'

function deviceName(): string {
  const ua = navigator.userAgent
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) return 'iPad'
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/Android/.test(ua)) return 'Android'
  return 'Браузер'
}

/** `LOMI-7241` or `LOMI7241`, case-insensitively; anything else is not a code. */
function parseLinkCode(raw: string): { word: string; pin: string } | null {
  const compact = raw.toUpperCase().replace(/-/g, '')
  const m = /^([A-Z]{4})(\d{4})$/.exec(compact)
  return m ? { word: m[1], pin: m[2] } : null
}

// Every attempt counts towards the hour lock, so concurrent callers (React
// StrictMode runs effects twice in development) must share one request.
const linkInFlight = new Map<string, ReturnType<typeof api.login>>()
function loginOnce(word: string, pin: string) {
  const key = `${word}-${pin}`
  let p = linkInFlight.get(key)
  if (!p) {
    p = api.login(word, pin, deviceName())
    p.catch(() => linkInFlight.delete(key))
    linkInFlight.set(key, p)
  }
  return p
}

// The mascot's box must actually shrink on a short screen (not just look
// smaller), so its size is chosen in JS rather than left to CSS.
function useShortScreen(): boolean {
  const [short, setShort] = useState(() => matchMedia('(max-height: 700px)').matches)
  useEffect(() => {
    const mq = matchMedia('(max-height: 700px)')
    const onChange = () => setShort(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return short
}

const LOCK_MS = 60 * 60 * 1000

function formatCountdown(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function BackspaceIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path
        d="M9 5h10a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-6-7z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      <path d="M11.5 9.5l5 5M16.5 9.5l-5 5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

const LETTERS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('')

function LetterKeys({
  disabled,
  onLetter,
  onBackspace,
}: {
  disabled: boolean
  onLetter: (letter: string) => void
  onBackspace: () => void
}) {
  return (
    <div className={`keys${disabled ? ' dim' : ''}`} aria-label="Буквы">
      {LETTERS.map((l) => (
        <button key={l} type="button" className="key" disabled={disabled} onClick={() => onLetter(l)}>
          {l}
        </button>
      ))}
      <button type="button" className="key w2" aria-label="Стереть" disabled={disabled} onClick={onBackspace}>
        <BackspaceIcon />
      </button>
    </div>
  )
}

function DigitKeys({
  disabled,
  onDigit,
  onBackspace,
  onAbc,
}: {
  disabled: boolean
  onDigit: (digit: string) => void
  onBackspace: () => void
  onAbc: () => void
}) {
  return (
    <div className={`keys digits${disabled ? ' dim' : ''}`} aria-label="Цифры">
      {[1, 2, 3, 4, 5, 6, 7, 8, 9].map((n) => (
        <button key={n} type="button" className="key" disabled={disabled} onClick={() => onDigit(String(n))}>
          {n}
        </button>
      ))}
      <button type="button" className="key sw" aria-label="К буквам" disabled={disabled} onClick={onAbc}>
        ABC
      </button>
      <button type="button" className="key" disabled={disabled} onClick={() => onDigit('0')}>
        0
      </button>
      <button type="button" className="key" aria-label="Стереть" disabled={disabled} onClick={onBackspace}>
        <BackspaceIcon />
      </button>
    </div>
  )
}

function CodeCells({
  value,
  cursor,
  bad = false,
  ro = false,
}: {
  value: string
  cursor: boolean
  bad?: boolean
  ro?: boolean
}) {
  const chars = [...value]
  const at = cursor && !ro && chars.length < 8 ? chars.length : -1
  const onLet = at >= 0 && at < 4
  const onNum = at >= 4 || (!ro && chars.length >= 4)
  const cell = (i: number) => (
    <div key={i} className={`cell${i === at ? ' cur' : ''}${bad && i >= 4 ? ' bad' : ''}`}>
      {chars[i] ?? ''}
    </div>
  )
  return (
    <div className={`code${ro ? ' ro' : ''}${bad ? ' shake' : ''}`} aria-label="Код">
      <div className={`grp${onLet ? ' on' : ''}`}>
        <div className="cells">{[0, 1, 2, 3].map(cell)}</div>
        <small>буквы</small>
      </div>
      <div className="dash">–</div>
      <div className={`grp${onNum ? ' on' : ''}`}>
        <div className="cells">{[4, 5, 6, 7].map(cell)}</div>
        <small>цифры</small>
      </div>
    </div>
  )
}

function Pips({ left }: { left: number }) {
  return (
    <div className="pips" aria-hidden="true">
      {[0, 1, 2].map((i) => (
        <i key={i} className={i < left ? '' : 'gone'} />
      ))}
    </div>
  )
}

interface WrongCodeDetail {
  attempts_left: number
}
interface LockedDetail {
  locked_until: string
}

type ScreenKind = 'linkCheck' | 'linkOffline' | 'form' | 'locked' | 'success'
type Pad = 'let' | 'num'
type LockResolution = 'time' | 'parent' | null
type MsgState =
  | { kind: 'none' }
  | { kind: 'err' | 'linkBad'; attemptsLeft?: number }
  | { kind: 'offline' }
  | { kind: 'reopened' }

function describeMsg(msg: MsgState): { title: string; subtitle: string; pipsLeft?: number } | null {
  switch (msg.kind) {
    case 'none':
      return null
    case 'err': {
      const left = msg.attemptsLeft ?? 0
      return {
        title: 'Не тот код',
        subtitle:
          left <= 1 ? 'Последняя попытка — потом код закроется на час' : `Проверь буквы и цифры. Ещё ${left} попытки`,
        pipsLeft: left,
      }
    }
    case 'linkBad': {
      const left = msg.attemptsLeft
      return {
        title: 'Ссылка не сработала',
        subtitle:
          left == null
            ? 'Введи код вручную'
            : left <= 1
              ? 'Последняя попытка — потом код закроется на час'
              : `Введи код вручную. Ещё ${left} попытки`,
        pipsLeft: left,
      }
    }
    case 'offline':
      return { title: 'Нет связи', subtitle: 'Код не проверен, попытка не потрачена' }
    case 'reopened':
      return { title: 'Код открыт!', subtitle: 'Цифры теперь новые — посмотри в Telegram' }
  }
}

export function Login({ code, onLoggedIn }: { code: string | null; onLoggedIn: () => void }) {
  const short = useShortScreen()
  const linkCode = useMemo(() => (code ? parseLinkCode(code) : null), [code])

  const [screen, setScreen] = useState<ScreenKind>(() => (linkCode ? 'linkCheck' : 'form'))
  const [value, setValue] = useState('')
  const [pad, setPad] = useState<Pad>('let')
  const [msg, setMsg] = useState<MsgState>({ kind: 'none' })
  const [bad, setBad] = useState(false)
  const [busy, setBusy] = useState(false)
  const [lockedUntil, setLockedUntil] = useState<string | null>(null)
  const [lockResolution, setLockResolution] = useState<LockResolution>(null)
  const [lockWord, setLockWord] = useState<string | null>(null)
  const [now, setNow] = useState(() => Date.now())
  const [childName, setChildName] = useState('')

  function runLinkAttempt(word: string, pin: string, isCancelled: () => boolean = () => false) {
    setScreen('linkCheck')
    loginOnce(word, pin)
      .then((r) => {
        history.replaceState(null, '', '/')
        if (isCancelled()) return
        setToken(r.device_token)
        setChildName(r.child.name)
        setScreen('success')
      })
      .catch((e: unknown) => {
        history.replaceState(null, '', '/')
        if (isCancelled()) return
        if (e instanceof ApiError && e.status === 401) {
          setValue(word)
          setPad('num')
          setMsg({ kind: 'linkBad', attemptsLeft: (e.detail as WrongCodeDetail).attempts_left })
          setScreen('form')
        } else if (e instanceof ApiError && e.status === 423) {
          setLockedUntil((e.detail as LockedDetail).locked_until)
          setLockResolution(null)
          setScreen('locked')
        } else {
          setScreen('linkOffline')
        }
      })
  }

  // Submit the link's code exactly once, even under StrictMode's double effect.
  // Syncing with the server is the one legitimate reason to set state from an effect.
  useEffect(() => {
    if (!linkCode) return
    let cancelled = false
    // oxlint-disable-next-line react/set-state-in-effect
    runLinkAttempt(linkCode.word, linkCode.pin, () => cancelled)
    return () => {
      cancelled = true
    }
  }, [linkCode])

  // Success: show the greeting, then hand off to the home screen.
  useEffect(() => {
    if (screen !== 'success') return
    const id = setTimeout(onLoggedIn, 1200)
    return () => clearTimeout(id)
  }, [screen, onLoggedIn])

  // Locked: tick the countdown and poll the server for an early or on-time unlock.
  useEffect(() => {
    if (screen !== 'locked' || !lockedUntil || lockResolution) return
    let cancelled = false
    let zeroChecked = false
    const checkStatus = async () => {
      try {
        const status = await api.loginStatus()
        if (cancelled) return
        if (status.locked_until === null) {
          setLockWord(status.word)
          setLockResolution(status.pin_rotated ? 'parent' : 'time')
        }
      } catch {
        /* offline: the next scheduled check will retry */
      }
    }
    const tick = setInterval(() => {
      setNow(Date.now())
      if (!zeroChecked && new Date(lockedUntil).getTime() - Date.now() <= 0) {
        zeroChecked = true
        void checkStatus()
      }
    }, 1000)
    const poll = setInterval(() => void checkStatus(), 10000)
    return () => {
      cancelled = true
      clearInterval(tick)
      clearInterval(poll)
    }
  }, [screen, lockedUntil, lockResolution])

  function clearError() {
    if (msg.kind !== 'none' || bad) {
      setMsg({ kind: 'none' })
      setBad(false)
    }
  }

  function pressLetter(letter: string) {
    if (busy || value.length >= 4) return
    clearError()
    const nv = value + letter
    setValue(nv)
    if (nv.length === 4) setPad('num')
  }

  function pressDigit(digit: string) {
    if (busy || value.length < 4 || value.length >= 8) return
    clearError()
    setValue(value + digit)
  }

  function pressBackspace() {
    if (busy || value.length === 0) return
    clearError()
    const nv = value.slice(0, -1)
    setValue(nv)
    if (nv.length < 4) setPad('let')
  }

  function pressAbc() {
    setPad('let')
  }

  async function submit() {
    if (value.length !== 8 || busy || bad) return
    const word = value.slice(0, 4)
    const pin = value.slice(4, 8)
    setBusy(true)
    try {
      const r = await api.login(word, pin, deviceName())
      setToken(r.device_token)
      setChildName(r.child.name)
      setScreen('success')
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setBad(true)
        setMsg({ kind: 'err', attemptsLeft: (e.detail as WrongCodeDetail).attempts_left })
      } else if (e instanceof ApiError && e.status === 423) {
        setLockedUntil((e.detail as LockedDetail).locked_until)
        setLockResolution(null)
        setScreen('locked')
      } else {
        setMsg({ kind: 'offline' })
      }
    } finally {
      setBusy(false)
    }
  }

  function resumeAfterLock() {
    // Either way the letters stay and the digits start over.
    const word = lockResolution === 'parent' ? (lockWord ?? '') : value.slice(0, 4)
    setValue(word)
    setPad(word.length === 4 ? 'num' : 'let')
    setMsg(lockResolution === 'parent' ? { kind: 'reopened' } : { kind: 'none' })
    setBad(false)
    setLockedUntil(null)
    setLockResolution(null)
    setScreen('form')
  }

  const msgInfo = describeMsg(msg)
  const canSubmit = value.length === 8 && !busy && !bad
  // Clamped: the device clock may lag the server's, and "60:01" would look odd.
  const remainingMs = lockedUntil
    ? Math.min(LOCK_MS, Math.max(0, new Date(lockedUntil).getTime() - now))
    : 0
  const pct = Math.max(0, Math.min(100, (remainingMs / LOCK_MS) * 100))

  return (
    <div className="login">
      {screen === 'linkCheck' && linkCode && (
        <div className="mid">
          <Mascot size={short ? 64 : 96} />
          <h1>Проверяем код…</h1>
          <CodeCells value={linkCode.word + linkCode.pin} cursor={false} ro />
          <div className="bigspin" role="progressbar" aria-label="Проверяем" />
        </div>
      )}

      {screen === 'linkOffline' && linkCode && (
        <div className="mid">
          <Mascot size={short ? 64 : 96} />
          <h1>Нет связи</h1>
          <p>Проверь интернет — и попробуем ещё раз</p>
          <button type="button" className="play" onClick={() => runLinkAttempt(linkCode.word, linkCode.pin)}>
            Повторить
          </button>
        </div>
      )}

      {screen === 'form' && (
        <div className="lg">
          <div className="lg-head">
            <Mascot size={short ? 48 : 72} />
            <div>
              <h1>Введи код</h1>
              <p>
                Код есть у мамы или папы в&nbsp;<b>Telegram</b>
              </p>
            </div>
          </div>
          <CodeCells value={value} cursor={!busy && !bad} bad={bad} />
          <div
            className={`msg${msg.kind === 'reopened' ? ' info' : msg.kind === 'offline' ? ' offline' : ''}`}
            role="status"
            aria-live="polite"
          >
            {msgInfo && (
              <>
                <b>{msgInfo.title}</b>
                <span>{msgInfo.subtitle}</span>
                {msgInfo.pipsLeft != null && <Pips left={msgInfo.pipsLeft} />}
              </>
            )}
          </div>
          <div className="spacer" />
          {pad === 'let' ? (
            <LetterKeys disabled={busy} onLetter={pressLetter} onBackspace={pressBackspace} />
          ) : (
            <DigitKeys disabled={busy} onDigit={pressDigit} onBackspace={pressBackspace} onAbc={pressAbc} />
          )}
          <button
            type="button"
            className={`play${busy ? ' busy' : ''}`}
            disabled={!canSubmit}
            aria-busy={busy || undefined}
            onClick={submit}
          >
            {busy ? (
              <>
                <span className="spin" />
                Проверяем…
              </>
            ) : (
              'Войти'
            )}
          </button>
        </div>
      )}

      {screen === 'locked' && (
        <div className="mid">
          {lockResolution === null && (
            <>
              <Mascot size={short ? 64 : 96} />
              <h1>Код закрыт на&nbsp;час</h1>
              <p>Много ошибок подряд — так бывает. Немного отдохнём!</p>
              <div className="lock-card" role="timer" aria-label={`До открытия ${formatCountdown(remainingMs)}`}>
                <small>Откроется через</small>
                <span className="big-num">{formatCountdown(remainingMs)}</span>
                <div className="prog">
                  <i style={{ width: `${pct}%` }} />
                </div>
              </div>
              <div className="tip">
                <span>Попроси маму или папу открыть код в&nbsp;Telegram</span>
              </div>
            </>
          )}
          {lockResolution === 'time' && (
            <>
              <Mascot size={short ? 64 : 96} bounce={1} />
              <h1>Час прошёл!</h1>
              <p>Можно попробовать ещё раз</p>
              <button type="button" className="play" onClick={resumeAfterLock}>
                Попробовать снова
              </button>
            </>
          )}
          {lockResolution === 'parent' && (
            <>
              <Mascot size={short ? 64 : 96} bounce={1} />
              <h1>Код открыт!</h1>
              <p>Мама или папа открыли его в Telegram</p>
              <button type="button" className="play" onClick={resumeAfterLock}>
                Попробовать снова
              </button>
            </>
          )}
        </div>
      )}

      {screen === 'success' && (
        <div className="mid">
          <Mascot size={short ? 96 : 120} bounce={1} />
          <div className="hi">
            <span className="ka">გამარჯობა!</span>
            <h1>Привет, {childName}!</h1>
          </div>
          <p>Открываем уроки…</p>
        </div>
      )}
    </div>
  )
}
