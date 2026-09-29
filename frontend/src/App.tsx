import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, ApiError, getToken, setToken } from './api'
import { Speaker } from './audio'
import type { Busy } from './busy'
import { Hills } from './components/Mascot'
import { ReplaySheet } from './components/ReplaySheet'
import { Home } from './screens/Home'
import { Lesson } from './screens/Lesson'
import { Lessons } from './screens/Lessons'
import { Login } from './screens/Login'
import { ProgressMap } from './screens/ProgressMap'
import { StickerCard } from './screens/StickerCard'
import { registerAppServiceWorker } from './sw'
import type { LessonOut, Me, SessionOut, Step, TopicOut, WordOut } from './types'

type Screen =
  | { kind: 'login'; code: string | null }
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'home'; me: Me }

/** Which of the screens under the "home" state is shown; the menu opens only over 'home'. */
type View = 'home' | 'lessons' | 'map'

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
  /** The done lesson whose «Повторить» was tapped: the replay sheet is open for it. */
  const [replay, setReplay] = useState<LessonOut | null>(null)
  /** The sticker tapped on the progress map: its own page is open over the map. */
  const [sticker, setSticker] = useState<WordOut | null>(null)
  const [busy, setBusy] = useState<Busy>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const speaker = useMemo(() => new Speaker(), [])

  const loadMe = useCallback(async (pending?: Promise<Me>) => {
    try {
      setScreen({ kind: 'home', me: await (pending ?? api.me()) })
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        setToken(null)
        setScreen({ kind: 'login', code: null })
      } else {
        setScreen({ kind: 'error', message: 'Не удалось загрузить. Проверь интернет и попробуй ещё.' })
      }
    }
  }, [])

  const reload = useCallback(
    (pending?: Promise<Me>) => {
      setScreen({ kind: 'loading' })
      setView('home') // a fresh load always lands on the home screen
      setSticker(null)
      void loadMe(pending)
    },
    [loadMe],
  )

  // Initial load for an already logged-in device (the "loading" initial state).
  // Syncing with the server is the one legitimate reason to set state from an effect.
  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect
    if (getToken() && !loginCodeFromUrl()) void loadMe()
  }, [loadMe])

  // The service worker is registered once the home (or error) screen is up, not
  // at startup, so its precache doesn't compete with the login/me requests; the
  // login screen still has those ahead of it. Idempotent: safe to call again on
  // every later screen change.
  useEffect(() => {
    if (screen.kind !== 'home' && screen.kind !== 'error') return
    registerAppServiceWorker()
  }, [screen.kind])

  /** Ask the server for a session and open it; the replay sheet closes either way.
   *  `lesson` is the one whose button shows "Открываю…" meanwhile (null: review all). */
  const openSession = async (lesson: LessonOut | null, load: () => Promise<SessionOut>) => {
    setBusy({ lesson })
    setNotice(null)
    try {
      const s = await load()
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
        setNotice('Этот урок пока недоступен')
      } else {
        setNotice('Нет связи. Проверь интернет и попробуй ещё')
      }
    } finally {
      setBusy(null)
      setReplay(null)
    }
  }

  const startLesson = (lesson: LessonOut | null) =>
    openSession(lesson, () => api.startSession(lesson ? lesson.number : null))

  // Only reachable from the replay sheet, so `replay` is the lesson whose sheet is open.
  const restartTopic = (topic: TopicOut) => openSession(replay, () => api.restartTopic(topic.slug))

  const closeLesson = () => {
    setLesson(null)
    setView('home')
    reload()
  }

  const replayTopic =
    replay && screen.kind === 'home'
      ? screen.me.topics.find((t) => t.slug === replay.topic_slug)
      : undefined

  const openLessons = () => {
    setMenuOpen(false)
    setView('lessons')
  }

  const openMap = () => {
    setMenuOpen(false)
    setView('map')
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
            <button type="button" className="next" onClick={() => reload()}>
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
          onReplay={setReplay}
          menuOpen={menuOpen}
          onOpenMenu={() => setMenuOpen(true)}
          onCloseMenu={() => setMenuOpen(false)}
          onOpenLessons={openLessons}
          onOpenMap={openMap}
        />
      )}
      {screen.kind === 'home' && view === 'lessons' && (
        <Lessons
          me={screen.me}
          busy={busy}
          onPlay={startLesson}
          onReplay={setReplay}
          onBack={() => setView('home')}
        />
      )}
      {screen.kind === 'home' && view === 'map' && (
        <ProgressMap
          me={screen.me}
          onOpen={(word) => {
            // Sound must start inside the tap itself: iOS only allows programmatic
            // playback from a user gesture (see Speaker.unlock in audio.ts:30-33).
            speaker.preload([word])
            speaker.unlock()
            void speaker.play(word)
            setSticker(word)
          }}
          onBack={() => setView('home')}
        />
      )}
      {replay && replayTopic && screen.kind === 'home' && !lesson && (
        <ReplaySheet
          lesson={replay}
          topic={replayTopic}
          busy={busy !== null}
          onClose={() => setReplay(null)}
          onQuiz={startLesson}
          onRestart={restartTopic}
        />
      )}
      {sticker && screen.kind === 'home' && view === 'map' && (
        <StickerCard
          word={sticker}
          speaker={speaker}
          showHint={screen.me.settings.show_hint}
          onBack={() => setSticker(null)}
        />
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
