import { useState } from 'react'
import { fmtLari } from '../fx'
import type { LessonOut, Me } from '../types'
import { Emoji } from '../components/Emoji'
import { JarIcon, Mascot } from '../components/Mascot'
import { WordImage } from '../components/WordImage'
import { textClass } from '../wordText'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

function LockIcon() {
  return (
    <svg className="lock-i" viewBox="0 0 24 24" aria-label="закрыто">
      <rect x="4" y="10" width="16" height="11" rx="3" fill="currentColor" />
      <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeWidth="2.6" fill="none" strokeLinecap="round" />
    </svg>
  )
}

function LessonTitle({ lesson }: { lesson: LessonOut }) {
  return (
    <>
      {lesson.title_ru}
      {lesson.parts > 1 && <span className="part"> · {lesson.part}</span>}
    </>
  )
}

export function Home({
  me,
  busy,
  onPlay,
}: {
  me: Me
  busy: boolean
  onPlay: (lesson: LessonOut | null) => void
}) {
  const [expanded, setExpanded] = useState(false)
  const learnedTotal = me.stickers.filter((s) => s.learned).length

  const doneLessons = me.lessons.filter((l) => l.status === 'done')
  const current = me.lessons.find((l) => l.status === 'current')
  // Today's finished lessons can be replayed; offer the latest one.
  const playableDone = [...doneLessons].reverse().find((l) => l.playable)
  const lockedLessons = me.lessons.filter((l) => l.status === 'locked')
  const visibleLocked = lockedLessons.slice(0, 2)
  const restLocked = lockedLessons.length - visibleLocked.length

  return (
    <main className="wrap">
      <div className="hello">
        <Mascot />
        <div className="bubble">
          <span className="ka">გამარჯობა!</span>
          <small>гамарджоба! Я Мзико. Поиграем, {me.child.name}?</small>
        </div>
      </div>

      <div className="jar">
        <JarIcon />
        <div>
          <b>{me.week.coins}</b> <span className="jar-unit">монет</span>
          <div className="sub">это {fmtLari(me.week.lari)} ₾ на сладости</div>
        </div>
      </div>

      <div className="week" aria-label="Дни недели">
        {DAYS.map((label, i) => {
          const date = addDays(me.week.week_start, i)
          const done = me.week.study_days.includes(date)
          const today = date === me.week.today
          return (
            <div key={label} className={`day${done ? ' done' : ''}${today ? ' today' : ''}`}>
              {done ? '★' : label}
            </div>
          )
        })}
      </div>

      <div className="path">
        {doneLessons.length > 0 && (
          <div className="step">
            <button
              type="button"
              className="lsn fold"
              aria-expanded={expanded}
              onClick={() => setExpanded((e) => !e)}
            >
              <span className="num">✓</span>
              <span className="t">Пройдено {doneLessons.length} уроков</span>
              <span className="chev">{expanded ? '▾' : '▸'}</span>
            </button>
          </div>
        )}

        {expanded &&
          doneLessons.map((l) => (
            <div key={l.number} className="step">
              <div className="lsn done">
                <span className="num">✓</span>
                <span className="ic">
                  <Emoji value={l.icon} alt="" />
                </span>
                <span className="t">
                  <LessonTitle lesson={l} />
                </span>
              </div>
            </div>
          ))}

        {!current && (
          <div className="step">
            <div className="cur all">
              <Mascot size={88} />
              <b>Все уроки пройдены!</b>
              <small>{learnedTotal} слов выучено</small>
              <button
                type="button"
                className="play"
                disabled={busy || !me.review_available}
                onClick={() => onPlay(null)}
              >
                {me.review_available ? 'Повторить слова' : 'Всё закреплено!'}
              </button>
            </div>
          </div>
        )}

        {current && playableDone && current.playable && (
          <div className="step">
            <div className="lsn review">
              <span className="num">✓</span>
              <span className="ic">
                <Emoji value={playableDone.icon} alt="" />
              </span>
              <span className="t">
                <LessonTitle lesson={playableDone} />
              </span>
              <button
                type="button"
                className="mini-play"
                disabled={busy}
                onClick={() => onPlay(playableDone)}
              >
                Повторить
              </button>
            </div>
          </div>
        )}

        {current && playableDone && !current.playable && (
          <div className="step">
            <div className="cur">
              <div className="cur-h">
                <span className="num now">{playableDone.number}</span>
                <span className="ic">
                  <Emoji value={playableDone.icon} alt="" />
                </span>
                <div className="cur-t">
                  <b>
                    <LessonTitle lesson={playableDone} />
                  </b>
                </div>
              </div>
              <button type="button" className="play" disabled={busy} onClick={() => onPlay(playableDone)}>
                Повторить
              </button>
              <p className="soon">Новый урок — завтра</p>
            </div>
          </div>
        )}

        {current && (current.playable || !playableDone) && (
          <div className="step">
            <div className="cur">
              <div className="cur-h">
                <span className="num now">{current.number}</span>
                <span className="ic">
                  <Emoji value={current.icon} alt="" />
                </span>
                <div className="cur-t">
                  <b>
                    <LessonTitle lesson={current} />
                  </b>
                  <small>
                    показано {current.introduced} из {current.total}
                  </small>
                </div>
              </div>
              <div className="prog">
                <i style={{ width: `${Math.round((current.introduced / current.total) * 100)}%` }} />
              </div>
              {current.playable ? (
                <button type="button" className="play" disabled={busy} onClick={() => onPlay(current)}>
                  Играть
                </button>
              ) : (
                <p className="soon">Новый урок — завтра</p>
              )}
            </div>
          </div>
        )}

        {visibleLocked.map((l) => (
          <div key={l.number} className="step">
            <div className="lsn lock" aria-disabled="true">
              <span className="num">{l.number}</span>
              <span className="ic">
                <Emoji value={l.icon} alt="" />
              </span>
              <span className="t">
                <LessonTitle lesson={l} />
              </span>
              <LockIcon />
            </div>
          </div>
        ))}

        {restLocked > 0 && (
          <div className="step">
            <div className="more">Дальше ещё {restLocked} уроков</div>
          </div>
        )}
      </div>

      <div className="learned">
        Наклейки: {learnedTotal} из {me.stickers.length}
      </div>
      <div className="stickers">
        {me.stickers.map((s) => (
          <div
            key={`${s.word.topic_slug}/${s.word.slug}`}
            className={`stk${textClass(s.word)}${s.learned ? '' : ' lock'}`}
            title={s.word.ru}
          >
            <WordImage word={s.word} />
          </div>
        ))}
      </div>
    </main>
  )
}
