import { wordsW } from '../fx'
import type { LessonOut, Me, WordOut } from '../types'
import { Emoji } from '../components/Emoji'
import { BackIcon, LockIcon } from '../components/Icons'
import { Mascot } from '../components/Mascot'
import { WordImage } from '../components/WordImage'
import { textClass } from '../wordText'
import { lockedReason, SECTIONS } from '../sections'

/** Why a lesson's header still shows as locked: its topic is not open yet (`topic`, see
 *  `lockedReason`), or an earlier part of its topic is not finished yet (`part`). Only drives the
 *  dashed card and the timer text now — a locked lesson's stickers are simply not learned yet. */
type MapLock = 'topic' | 'part'

function lockOf(lesson: LessonOut): MapLock | null {
  if (lesson.status === 'locked') return 'part'
  if (!lesson.playable) return 'topic'
  return null
}

/** One lesson: its header (number, icon, title, progress) and its words as stickers — a learned
 *  one opens its own word, a grey one cannot be tapped. */
function LessonGroup({
  lesson,
  stickers,
  topics,
  onOpen,
}: {
  lesson: LessonOut
  stickers: Me['stickers']
  topics: Me['topics']
  onOpen: (word: WordOut) => void
}) {
  const lock = lockOf(lesson)
  const topic = topics.find((t) => t.slug === lesson.topic_slug)
  const done = lesson.status === 'done'
  const learned = stickers.filter((s) => s.learned).length
  const sub = done
    ? `выучено ${learned} из ${lesson.total}`
    : lesson.introduced > 0
      ? `показано ${lesson.introduced} из ${lesson.total}`
      : wordsW(lesson.total)

  return (
    <div className={`mapl${lock ? ' lock' : ''}`}>
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
        {lock ? (
          <span className="tmr">
            <LockIcon />
            {lock === 'topic' ? (topic ? lockedReason(topics, topic) : 'завтра') : `после ${lesson.part - 1}`}
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
            disabled={!s.learned}
            onClick={() => onOpen(s.word)}
          >
            <WordImage word={s.word} />
          </button>
        ))}
      </div>
    </div>
  )
}

/** «Карта прогресса»: every word of the programme as a sticker (learned ones in colour), grouped
 *  by lesson under the same three sections as the «Уроки» screen. A learned sticker opens its own
 *  word on a new page; a grey (not yet learned) one is disabled and does nothing. */
export function ProgressMap({
  me,
  onOpen,
  onBack,
}: {
  me: Me
  onOpen: (word: WordOut) => void
  onBack: () => void
}) {
  const learnedTotal = me.stickers.filter((s) => s.learned).length
  const sectionOf = new Map(me.topics.map((t) => [t.slug, t.section]))

  return (
    <main className="wrap">
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
          <small>
            {learnedTotal > 0
              ? 'Нажми на цветную наклейку — услышишь слово'
              : 'Выучи слово — наклейка станет цветной'}
          </small>
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
                  topics={me.topics}
                  onOpen={onOpen}
                />
              ))}
            </div>
          </section>
        )
      })}
    </main>
  )
}
