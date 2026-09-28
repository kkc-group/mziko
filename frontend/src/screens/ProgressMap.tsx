import { wordsW } from '../fx'
import type { LessonOut, Me } from '../types'
import { Emoji } from '../components/Emoji'
import { BackIcon, LockIcon } from '../components/Icons'
import { Mascot } from '../components/Mascot'
import { BusyLabel } from '../components/PlayButton'
import { WordImage } from '../components/WordImage'
import { isBusyFor, type Busy } from '../busy'
import { textClass } from '../wordText'
import { SECTIONS } from '../sections'

/** Why a lesson's stickers do not open it today: another topic of its section was chosen
 *  (`topic`), or an earlier part of its topic is not finished yet (`part`). */
export type MapLock = 'topic' | 'part'

function lockOf(lesson: LessonOut): MapLock | null {
  if (lesson.status === 'locked') return 'part'
  if (!lesson.playable) return 'topic'
  return null
}

/** One lesson: its header (number, icon, title, progress) and its words as tappable stickers. */
function LessonGroup({
  lesson,
  stickers,
  busy,
  onTap,
}: {
  lesson: LessonOut
  stickers: Me['stickers']
  busy: Busy
  onTap: (lesson: LessonOut) => void
}) {
  const lock = lockOf(lesson)
  const mine = isBusyFor(busy, lesson)
  const done = lesson.status === 'done'
  const learned = stickers.filter((s) => s.learned).length
  const sub = done
    ? `выучено ${learned} из ${lesson.total}`
    : lesson.introduced > 0
      ? `показано ${lesson.introduced} из ${lesson.total}`
      : wordsW(lesson.total)

  return (
    <div className={`mapl${lock ? ' lock' : ''}`} aria-busy={mine || undefined}>
      <div className="cur-h">
        <span className={`num${done ? ' ok' : ''}`}>{done ? '✓' : lesson.number}</span>
        <span className="ic">
          <Emoji value={lesson.icon} alt="" />
        </span>
        <div className="cur-t">
          <b>
            {lesson.title_ru}
            {lesson.parts > 1 && <span className="part"> · {lesson.part}</span>}
          </b>
          <small>{sub}</small>
        </div>
        {mine ? (
          <span className="mini-play busy">
            <BusyLabel />
          </span>
        ) : lock ? (
          <span className="tmr">
            <LockIcon />
            {lock === 'topic' ? 'завтра' : `после ${lesson.part - 1}`}
          </span>
        ) : null}
      </div>
      <div className="stickers">
        {stickers.map((s) => (
          <button
            type="button"
            key={`${s.word.topic_slug}/${s.word.slug}`}
            className={`stk${textClass(s.word)}${s.learned ? '' : ' lock'}`}
            title={s.word.ru}
            aria-label={s.word.ru}
            onClick={() => onTap(lesson)}
          >
            <WordImage word={s.word} />
          </button>
        ))}
      </div>
    </div>
  )
}

/** «Карта прогресса»: every word of the programme as a sticker (learned ones in colour), grouped
 *  by lesson under the same three sections as the «Уроки» screen. A sticker opens its lesson:
 *  a done lesson goes to the replay sheet, the current one starts, a locked one only explains. */
export function ProgressMap({
  me,
  busy,
  onPlay,
  onReplay,
  onLocked,
  onBack,
}: {
  me: Me
  busy: Busy
  onPlay: (lesson: LessonOut) => void
  onReplay: (lesson: LessonOut) => void
  onLocked: (lock: MapLock) => void
  onBack: () => void
}) {
  const learnedTotal = me.stickers.filter((s) => s.learned).length
  const sectionOf = new Map(me.topics.map((t) => [t.slug, t.section]))

  const tap = (lesson: LessonOut) => {
    const lock = lockOf(lesson)
    if (lock) onLocked(lock)
    else if (lesson.status === 'done') onReplay(lesson)
    else onPlay(lesson)
  }

  return (
    <main className="wrap">
      {/* While a session opens, every tap but the busy button's lands here (see PlayButton). */}
      {busy && <div className="scrim" aria-hidden="true" />}
      <div className="topbar">
        <button type="button" className="x" aria-label="На главную" onClick={onBack}>
          <BackIcon />
        </button>
        <h1>Карта прогресса</h1>
      </div>

      <div className="lhello">
        <Mascot size={64} />
        <div className="bubble">
          Наклейки: {learnedTotal} из {me.stickers.length}
          <small>Нажми на наклейку — откроется её урок</small>
        </div>
      </div>

      {SECTIONS.map((section) => {
        const lessons = me.lessons.filter((l) => sectionOf.get(l.topic_slug) === section.key)
        if (lessons.length === 0) return null
        return (
          <section className="sec" key={section.key}>
            <div className="sech">
              <Emoji value={section.icon} alt="" />
              {section.title}
            </div>
            <div className="rows">
              {lessons.map((lesson) => (
                <LessonGroup
                  key={lesson.number}
                  lesson={lesson}
                  stickers={me.stickers.filter((s) => s.lesson === lesson.number)}
                  busy={busy}
                  onTap={tap}
                />
              ))}
            </div>
          </section>
        )
      })}
    </main>
  )
}
