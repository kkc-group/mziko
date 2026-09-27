import { useCallback, useEffect, useRef, useState } from 'react'
import { api, withRetry, type AnswerBody } from '../api'
import type { Speaker } from '../audio'
import { flyCoins, fmtLari, uuid } from '../fx'
import type { SessionSummary, Step, WordOut } from '../types'
import { JarIcon, Mascot } from '../components/Mascot'
import { SpeakButton } from '../components/SpeakButton'
import { WordImage } from '../components/WordImage'

type Toast = { kind: 'good' | 'try' | 'offline'; text: string } | null

export function Lesson({
  sessionId,
  steps,
  speaker,
  showHint,
  initialCoins,
  onClose,
  onDone,
}: {
  sessionId: string
  steps: Step[]
  speaker: Speaker
  showHint: boolean
  initialCoins: number
  onClose: () => void
  onDone: () => void
}) {
  const [idx, setIdx] = useState(0)
  const [coins, setCoins] = useState(initialCoins)
  const [toast, setToast] = useState<Toast>(null)
  const [bounce, setBounce] = useState(0)
  const [summary, setSummary] = useState<SessionSummary | null>(null)
  const [retry, setRetry] = useState<(() => void) | null>(null)
  const jarRef = useRef<HTMLDivElement>(null)

  const step: Step | undefined = steps[idx]
  const finished = idx >= steps.length

  // Auto-play the word when a card or a listen task appears.
  useEffect(() => {
    if (!step || step.type === 'recall') return
    const t = setTimeout(() => void speaker.play(step.word), 300)
    return () => clearTimeout(t)
  }, [step, speaker])

  // Finish the session once every step is done.
  useEffect(() => {
    if (!finished || summary) return
    let cancelled = false
    const run = async () => {
      try {
        const s = await withRetry(() => api.finish(sessionId))
        if (!cancelled) setSummary(s)
      } catch {
        if (!cancelled) {
          setToast({ kind: 'offline', text: 'Нет связи. Проверь интернет' })
          setRetry(() => run)
        }
      }
    }
    void run()
    return () => {
      cancelled = true
    }
  }, [finished, sessionId, summary])

  const next = useCallback(() => {
    setToast(null)
    setRetry(null)
    setIdx((i) => i + 1)
  }, [])

  return (
    <div className="lesson" role="dialog" aria-label="Занятие">
      <div className="lbar">
        <button type="button" className="x" aria-label="Закрыть" onClick={() => { speaker.stop(); onClose() }}>
          ✕
        </button>
        <div className="prog">
          <i style={{ width: `${(Math.min(idx, steps.length) / steps.length) * 100}%` }} />
        </div>
        <div className="minijar" ref={jarRef}>
          <JarIcon />
          <span>{coins}</span>
        </div>
      </div>

      <div className="stage">
        {finished ? (
          <Done summary={summary} coins={coins} onHome={onDone} />
        ) : step.type === 'intro' ? (
          <Intro step={step} speaker={speaker} showHint={showHint} onNext={next} />
        ) : (
          <Quiz
            key={idx}
            step={step}
            speaker={speaker}
            showHint={showHint}
            onError={(message) => setToast({ kind: 'offline', text: `Что-то сломалось: ${message}` })}
            onAnswer={async (chosen, attempt, el) => {
              const correct = chosen.slug === step.word.slug
              if (!correct) {
                setToast({ kind: 'try', text: 'Почти! Попробуй ещё' })
                void speaker.play(step.word)
                return false
              }
              void speaker.play(step.word)
              const body: AnswerBody = {
                step_index: idx,
                word_slug: chosen.slug,
                attempt,
                client_answer_id: uuid(),
              }
              const send = async () => {
                setToast(null)
                setRetry(null)
                try {
                  const r = await withRetry(() => api.answer(sessionId, body))
                  if (r.coins_gained && jarRef.current) flyCoins(el, jarRef.current, r.coins_gained)
                  setCoins(r.week_coins)
                  setBounce((n) => n + 1)
                  setToast({
                    kind: 'good',
                    text: r.word_learned
                      ? `Слово выучено! +${r.coins_gained} 🪙`
                      : r.coins_gained
                        ? `Молодец! +${r.coins_gained} 🪙`
                        : 'Правильно!',
                  })
                  setTimeout(next, r.word_learned ? 1700 : 1200)
                } catch {
                  setToast({ kind: 'offline', text: 'Нет связи. Проверь интернет' })
                  setRetry(() => send)
                }
              }
              await send()
              return true
            }}
          />
        )}
      </div>

      <div className={`toast${toast ? ` ${toast.kind}` : ''}`} aria-live="polite">
        {toast?.kind === 'good' && <Mascot bounce={bounce} size={44} />}
        {toast?.text}
        {retry && (
          <button type="button" className="retry" onClick={retry}>
            Повторить
          </button>
        )}
      </div>
    </div>
  )
}

function Intro({
  step,
  speaker,
  showHint,
  onNext,
}: {
  step: Step
  speaker: Speaker
  showHint: boolean
  onNext: () => void
}) {
  return (
    <>
      <p className="prompt">Новое слово!</p>
      <div className="pic">
        <WordImage word={step.word} />
      </div>
      <div className="word">
        <span className="ka">{step.word.ka}</span>
        {showHint && <span className="tr">{step.word.tr}</span>}
      </div>
      <SpeakButton word={step.word} speaker={speaker} />
      <button type="button" className="next" onClick={onNext}>
        Дальше
      </button>
    </>
  )
}

function Quiz({
  step,
  speaker,
  showHint,
  onAnswer,
  onError,
}: {
  step: Step
  speaker: Speaker
  showHint: boolean
  onAnswer: (chosen: WordOut, attempt: number, el: HTMLElement) => Promise<boolean>
  onError: (message: string) => void
}) {
  const [wrong, setWrong] = useState<string[]>([])
  const [okSlug, setOkSlug] = useState<string | null>(null)
  const locked = okSlug !== null

  const pick = async (o: WordOut, el: HTMLElement) => {
    if (locked || wrong.includes(o.slug)) return
    const attempt = wrong.length + 1
    try {
      const correct = await onAnswer(o, attempt, el)
      if (correct) setOkSlug(o.slug)
      else setWrong((w) => [...w, o.slug])
    } catch (e) {
      // Never leave the child on a frozen screen: surface the failure instead.
      console.error(e)
      onError(e instanceof Error ? e.message : String(e))
    }
  }

  const cls = (o: WordOut, base: string) =>
    `${base}${o.slug === okSlug ? ' ok' : ''}${wrong.includes(o.slug) ? ' bad' : ''}`

  if (step.type === 'listen') {
    return (
      <>
        <p className="prompt">Послушай и найди</p>
        <SpeakButton word={step.word} speaker={speaker} label="Послушать ещё раз" />
        <div className="grid">
          {step.options.map((o) => (
            <button
              key={o.slug}
              type="button"
              className={cls(o, 'tile')}
              disabled={locked || wrong.includes(o.slug)}
              aria-label={o.ru}
              onClick={(e) => void pick(o, e.currentTarget)}
            >
              <WordImage word={o} />
            </button>
          ))}
        </div>
      </>
    )
  }

  return (
    <>
      <p className="prompt">Как это по-грузински?</p>
      <div className="pic">
        <WordImage word={step.word} />
      </div>
      <div className="opts">
        {step.options.map((o) => (
          <div className="opt" key={o.slug}>
            <SpeakButton word={o} speaker={speaker} small />
            <button
              type="button"
              className={cls(o, 'ans')}
              disabled={locked || wrong.includes(o.slug)}
              onClick={(e) => void pick(o, e.currentTarget)}
            >
              <span className="ka">{o.ka}</span>
              {showHint && <small>{o.tr}</small>}
            </button>
          </div>
        ))}
      </div>
    </>
  )
}

function Done({
  summary,
  coins,
  onHome,
}: {
  summary: SessionSummary | null
  coins: number
  onHome: () => void
}) {
  return (
    <>
      <div className="done-screen">
        <h2>Ура, занятие готово!</h2>
        {summary ? (
          <>
            <div className="big-num">+{summary.coins_gained} 🪙</div>
            <p className="muted strong">
              В копилке {summary.week_coins} монет — это {fmtLari(summary.week_lari)} ₾
            </p>
            {summary.learned.length ? (
              <>
                <p className="strong">Новые наклейки:</p>
                <div className="stickers">
                  {summary.learned.map((w) => (
                    <div className="stk" key={`${w.topic_slug}/${w.slug}`} title={w.ru}>
                      <WordImage word={w} />
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <p className="muted">Приходи завтра — слова вернутся, и за них будут наклейки.</p>
            )}
          </>
        ) : (
          <p className="muted strong">В копилке {coins} монет. Сохраняю…</p>
        )}
      </div>
      <button type="button" className="next" onClick={onHome} disabled={!summary}>
        Домой
      </button>
    </>
  )
}
