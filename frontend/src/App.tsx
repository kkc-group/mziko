import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, getToken, setToken } from './api'
import { Speaker } from './audio'
import { Hills } from './components/Mascot'
import { Home } from './screens/Home'
import { Lesson } from './screens/Lesson'
import { Lessons } from './screens/Lessons'
import { Login } from './screens/Login'
import type { LessonOut, Me, Step } from './types'

type Screen =
  | { kind: 'login'; code: string | null }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'home'; me: Me }

/** Which of the two screens under the "home" state is shown; the menu opens only over 'home'. */
type View = 'home' | 'lessons'

interface ActiveLesson {
  sessionId: string
  steps: Step[]
}

/** `/c/LOMI-7241` from the bot: the login code, the screen submits it itself. */
function loginCodeFromUrl(): string | null {
  const m = location.pathname.match(/^\/c\/([^/]+)\/?$/)
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
    const loginCode = loginCodeFromUrl()
    if (loginCode) return { kind: 'login', code: loginCode }
    adoptTokenFromUrl()
    return getToken() ? { kind: 'loading' } : { kind: 'login', code: null }
  })
  const [view, setView] = useState<View>('home')
  const [menuOpen, setMenuOpen] = useState(false)
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
        setScreen({ kind: 'login', code: null })
      } else {
        setScreen({ kind: 'error', message: 'Не удалось загрузить. Проверь интернет и попробуй ещё.' })
      }
    }
  }, [])

  const reload = useCallback(() => {
    setScreen({ kind: 'loading' })
    setView('home') // a fresh load always lands on the home screen
    void loadMe()
  }, [loadMe])

  // Initial load for an already logged-in device (the "loading" initial state).
  // Syncing with the server is the one legitimate reason to set state from an effect.
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect
    if (getToken() && !loginCodeFromUrl()) void loadMe()
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
        setScreen({ kind: 'login', code: null })
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
    setView('home')
    reload()
  }

  const openLessons = () => {
    setMenuOpen(false)
    setView('lessons')
  }

  return (
    <>
      <Hills />
      {screen.kind === 'login' && <Login code={screen.code} onLoggedIn={reload} />}
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
      {screen.kind === 'home' && view === 'home' && (
        <Home
          me={screen.me}
          busy={busy}
          onPlay={startLesson}
          menuOpen={menuOpen}
          onOpenMenu={() => setMenuOpen(true)}
          onCloseMenu={() => setMenuOpen(false)}
          onOpenLessons={openLessons}
        />
      )}
      {screen.kind === 'home' && view === 'lessons' && (
        <Lessons me={screen.me} busy={busy} onPlay={startLesson} onBack={() => setView('home')} />
      )}
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
