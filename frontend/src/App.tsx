import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, getToken, setToken } from './api'
import { Speaker } from './audio'
import { Hills } from './components/Mascot'
import { Home } from './screens/Home'
import { Lesson } from './screens/Lesson'
import { Pair, Unpaired } from './screens/Pair'
import type { LessonOut, Me, Step } from './types'

type Screen =
  | { kind: 'pair'; code: string }
  | { kind: 'unpaired' }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'home'; me: Me }

interface ActiveLesson {
  sessionId: string
  steps: Step[]
}

function pairCodeFromUrl(): string | null {
  const m = location.pathname.match(/^\/pair\/([^/]+)\/?$/)
  return m ? decodeURIComponent(m[1]) : null
}

/** `/?token=…` stores a ready device token (testing without the bot) and cleans the URL. */
function adoptTokenFromUrl(): void {
  const token = new URLSearchParams(location.search).get('token')
  if (!token) return
  setToken(token)
  history.replaceState(null, '', location.pathname)
}

export default function App() {
  const [screen, setScreen] = useState<Screen>(() => {
    const code = pairCodeFromUrl()
    if (code) return { kind: 'pair', code }
    adoptTokenFromUrl()
    return getToken() ? { kind: 'loading' } : { kind: 'unpaired' }
  })
  const [lesson, setLesson] = useState<ActiveLesson | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const speaker = useMemo(() => new Speaker(), [])

  const loadMe = useCallback(async () => {
    try {
      setScreen({ kind: 'home', me: await api.me() })
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setToken(null)
        setScreen({ kind: 'unpaired' })
      } else {
        setScreen({ kind: 'error', message: 'Не удалось загрузить. Проверь интернет и попробуй ещё.' })
      }
    }
  }, [])

  const reload = useCallback(() => {
    setScreen({ kind: 'loading' })
    void loadMe()
  }, [loadMe])

  // Initial load for an already paired device (the "loading" initial state).
  // Syncing with the server is the one legitimate reason to set state from an effect.
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect
    if (getToken() && !pairCodeFromUrl()) void loadMe()
  }, [loadMe])

  const startLesson = async (lesson: LessonOut | null) => {
    setBusy(true)
    setNotice(null)
    try {
      const s = await api.startSession(lesson ? lesson.number : null)
      if (!s.session_id || s.steps.length === 0) {
        setNotice('На сегодня всё! Завтра новые слова')
        await loadMe()
        return
      }
      const words = s.steps.flatMap((st) => [st.word, ...st.options])
      speaker.preload(words)
      speaker.unlock()
      setLesson({ sessionId: s.session_id, steps: s.steps })
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setToken(null)
        setScreen({ kind: 'unpaired' })
      } else if (e instanceof ApiError && e.status === 409) {
        setNotice('Этот урок откроется завтра')
      } else {
        setNotice('Нет связи. Проверь интернет и попробуй ещё')
      }
    } finally {
      setBusy(false)
    }
  }

  const closeLesson = () => {
    setLesson(null)
    reload()
  }

  return (
    <>
      <Hills />
      {screen.kind === 'pair' && <Pair code={screen.code} onPaired={reload} />}
      {screen.kind === 'unpaired' && <Unpaired />}
      {screen.kind === 'loading' && <main className="wrap center"><p className="muted">Загружаю…</p></main>}
      {screen.kind === 'error' && (
        <main className="wrap center">
          <div className="card">
            <p className="muted">{screen.message}</p>
            <button type="button" className="next" onClick={reload}>
              Повторить
            </button>
          </div>
        </main>
      )}
      {screen.kind === 'home' && <Home me={screen.me} busy={busy} onPlay={startLesson} />}
      {notice && (
        <div className="notice" role="status" onClick={() => setNotice(null)}>
          {notice}
        </div>
      )}
      {lesson && screen.kind === 'home' && (
        <Lesson
          sessionId={lesson.sessionId}
          steps={lesson.steps}
          speaker={speaker}
          showHint={screen.me.settings.show_hint}
          initialCoins={screen.me.week.coins}
          onClose={closeLesson}
          onDone={closeLesson}
        />
      )}
    </>
  )
}
