import { useCallback, useEffect, useRef, useState } from 'react'
import { api, withRetry, type AnswerBody } from '../api'
import type { Speaker } from '../audio'
import { flyCoins, fmtLari, uuid } from '../fx'
import type { AnchorOut, SessionSummary, Step, WordOut } from '../types'
import { Emoji } from '../components/Emoji'
import { JarIcon, Mascot } from '../components/Mascot'
import { SpeakButton } from '../components/SpeakButton'
import { WordImage } from '../components/WordImage'
import { isLetter, isText, textClass } from '../wordText'

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
                // The child hears what they actually picked, then that it was wrong.
                await speaker.playThrough(chosen)
                await speaker.phrase('wrong')
                return false
              }
              void speaker.phrase('correct')
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
                  // A plain correct answer shows only the green check on the card (see Reveal).
                  const text = r.word_learned
                    ? `${isLetter(step.word) ? 'Буква выучена' : 'Слово выучено'}! +${r.coins_gained} 🪙`
                    : r.coins_gained
                      ? `Молодец! +${r.coins_gained} 🪙`
                      : null
                  setToast(text ? { kind: 'good', text } : null)
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
  const { word } = step
  const letter = isLetter(word)
  return (
    <>
      <p className="prompt">{letter ? 'Новая буква!' : 'Новое слово!'}</p>
      <div className={`pic${textClass(word)}`}>
        <WordImage word={word} />
      </div>
      {/* A text card already shows the word in the picture slot: do not repeat it below. */}
      {(!isText(word) || showHint) && (
        <div className="word">
          {!isText(word) && <span className="ka">{word.ka}</span>}
          {showHint && <span className="tr">{word.tr}</span>}
        </div>
      )}
      {word.anchor && <Anchor letter={word.image.value} anchor={word.anchor} showHint={showHint} />}
      <SpeakButton word={word} speaker={speaker} />
      <button type="button" className="next" onClick={onNext}>
        Дальше
      </button>
    </>
  )
}

/** "ბ as in ⚽ ბურთი": the example word under a letter, its first letter highlighted. */
function Anchor({ letter, anchor, showHint }: { letter: string; anchor: AnchorOut; showHint: boolean }) {
  const rest = anchor.ka.startsWith(letter) ? anchor.ka.slice(letter.length) : anchor.ka
  return (
    <div className="anchor" aria-label={`${anchor.ka} — ${anchor.ru}`}>
      {anchor.emoji ? <Emoji value={anchor.emoji} alt={anchor.ru} /> : <small>{anchor.ru}</small>}
      <span className="ka">
        {rest === anchor.ka ? anchor.ka : <><b>{letter}</b>{rest}</>}
      </span>
      {showHint && <small>{anchor.tr}</small>}
    </div>
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
  // The tapped option, shown large over the options while the screen is locked.
  const [picked, setPicked] = useState<{ word: WordOut; verdict: 'ok' | 'bad' | null } | null>(null)
  const locked = okSlug !== null || picked !== null

  const pick = async (o: WordOut, el: HTMLElement) => {
    if (locked || wrong.includes(o.slug)) return
    const attempt = wrong.length + 1
    setPicked({ word: o, verdict: null }) // locks every option at once: no double tap
    try {
      const correct = await onAnswer(o, attempt, el)
      if (correct) {
        setOkSlug(o.slug)
        setPicked({ word: o, verdict: 'ok' }) // stays until the next step
      } else {
        setWrong((w) => [...w, o.slug])
        setPicked({ word: o, verdict: 'bad' })
        setTimeout(() => setPicked(null), 400) // the red card fades, the rest unlock
      }
    } catch (e) {
      // Never leave the child on a frozen screen: surface the failure instead.
      console.error(e)
      setPicked(null)
      onError(e instanceof Error ? e.message : String(e))
    }
  }

  const cls = (o: WordOut, base: string) =>
    `${base}${o.slug === okSlug ? ' ok' : ''}${wrong.includes(o.slug) ? ' bad' : ''}`
  const dim = picked ? ' dim' : ''

  if (step.type === 'listen') {
    return (
      <>
        <p className="prompt">Послушай и найди</p>
        <div className={dim}>
          <SpeakButton word={step.word} speaker={speaker} label="Послушать ещё раз" />
        </div>
        <div className="grid-wrap">
          <div className={`grid${dim}`}>
            {step.options.map((o) => (
              <button
                key={o.slug}
                type="button"
                className={cls(o, `tile${textClass(o)}`)}
                disabled={locked || wrong.includes(o.slug)}
                aria-label={o.ru}
                onClick={(e) => void pick(o, e.currentTarget)}
              >
                <WordImage word={o} />
              </button>
            ))}
          </div>
          {picked && <Reveal word={picked.word} verdict={picked.verdict} />}
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
      <div className="grid-wrap">
        <div className={`opts${dim}`}>
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
        {picked && <Reveal word={picked.word} verdict={picked.verdict} asText />}
      </div>
    </>
  )
}

/** The tapped option, large over the options: neutral while the answer is in flight, then ok/bad. */
function Reveal({
  word,
  verdict,
  asText = false,
}: {
  word: WordOut
  verdict: 'ok' | 'bad' | null
  asText?: boolean
}) {
  const shape = asText ? ' txt' : textClass(word)
  return (
    <div className="reveal" aria-hidden="true">
      <div className={`pic${shape}${verdict ? ` ${verdict}` : ''}`}>
        {asText ? <span className="glyph w ka">{word.ka}</span> : <WordImage word={word} />}
        {verdict === 'ok' && (
          <span className="check">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 13l5 5L19 7" fill="none" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        )}
      </div>
    </div>
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
                    <div className={`stk${textClass(w)}`} key={`${w.topic_slug}/${w.slug}`} title={w.ru}>
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
