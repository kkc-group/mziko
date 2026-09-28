import { lessonsW, wordsW } from '../fx'
import type { LessonOut, Me, TopicOut } from '../types'
import { Emoji } from '../components/Emoji'
import { BackIcon, LockIcon } from '../components/Icons'
import { Mascot } from '../components/Mascot'
import { BusyLabel, PlayButton } from '../components/PlayButton'
import { isBusyFor, type Busy } from '../busy'

const SECTIONS: { key: TopicOut['section']; title: string; icon: string }[] = [
  { key: 'letters', title: 'Буквы', icon: '🔤' },
  { key: 'syllables', title: 'Слоги', icon: '🧩' },
  { key: 'words', title: 'Слова', icon: '💬' },
]

/** "Все буквы/слоги/слова пройдены" — the word varies by section. */
const ALL_DONE_LABEL: Record<TopicOut['section'], string> = {
  letters: 'буквы',
  syllables: 'слоги',
  words: 'слова',
}

function topicLessons(me: Me, slug: string): LessonOut[] {
  return me.lessons.filter((l) => l.topic_slug === slug)
}

/** The lesson to open for a topic: its first unfinished lesson, else its last. */
function topicLesson(lessons: LessonOut[]): LessonOut {
  return lessons.find((l) => l.status !== 'done') ?? lessons[lessons.length - 1]
}

function topicMeta(lessons: LessonOut[]): string {
  const words = lessons.reduce((a, l) => a + l.total, 0)
  return lessons.length > 1 ? `${lessonsW(lessons.length)} · ${wordsW(words)}` : wordsW(words)
}

function LessonTitle({ lesson }: { lesson: LessonOut }) {
  return (
    <>
      {lesson.title_ru}
      {lesson.parts > 1 && <span className="part"> · {lesson.part}</span>}
    </>
  )
}

function IconWithCheck({ icon, done }: { icon: string; done: boolean }) {
  return (
    <span className="icw">
      <span className="ic">
        <Emoji value={icon} alt="" />
      </span>
      {done && <i className="ok-b">✓</i>}
    </span>
  )
}

function OpenRow({
  topic,
  lessons,
  busy,
  onPlay,
}: {
  topic: TopicOut
  lessons: LessonOut[]
  busy: Busy
  onPlay: (lesson: LessonOut) => void
}) {
  const target = topicLesson(lessons)
  const mine = isBusyFor(busy, target)
  return (
    <button type="button" className="lsn" aria-busy={mine || undefined} onClick={() => onPlay(target)}>
      <IconWithCheck icon={topic.icon} done={topic.done} />
      <span className="t">
        {topic.title_ru}
        <small>{topicMeta(lessons)}</small>
      </span>
      <span className={`mini-play${mine ? ' busy' : ''}`}>
        {mine ? <BusyLabel /> : topic.done ? 'Повторить' : 'Играть'}
      </span>
    </button>
  )
}

function LockedRow({ topic, lessons }: { topic: TopicOut; lessons: LessonOut[] }) {
  return (
    <div className="lsn lock" aria-disabled="true">
      <IconWithCheck icon={topic.icon} done={topic.done} />
      <span className="t">
        {topic.title_ru}
        <small>{topicMeta(lessons)}</small>
      </span>
      <span className="tmr">
        <LockIcon />
        завтра
      </span>
    </div>
  )
}

/** The topic-of-the-day card: one card for a single-lesson topic, or a header plus one row
 *  per lesson (done/current/locked) for a multi-lesson one. */
function TodayCard({
  topic,
  lessons,
  busy,
  onPlay,
}: {
  topic: TopicOut
  lessons: LessonOut[]
  busy: Busy
  onPlay: (lesson: LessonOut) => void
}) {
  if (lessons.length === 1) {
    const l = lessons[0]
    const finished = l.status === 'done'
    const shown = l.introduced > 0
    const sub = finished
      ? `показано ${l.total} из ${l.total}`
      : shown
        ? `показано ${l.introduced} из ${l.total}`
        : wordsW(l.total)
    const pct = finished ? 100 : Math.round((l.introduced / l.total) * 100)
    return (
      <div className="cur">
        <div className="cur-h">
          <IconWithCheck icon={topic.icon} done={topic.done} />
          <div className="cur-t">
            <b>{topic.title_ru}</b>
            <small>{sub}</small>
          </div>
        </div>
        {(shown || finished) && (
          <div className="prog">
            <i style={{ width: `${pct}%` }} />
          </div>
        )}
        <PlayButton lesson={l} busy={busy} label={finished ? 'Повторить' : 'Играть'} onClick={() => onPlay(l)} />
      </div>
    )
  }

  const current = lessons.find((l) => l.status === 'current')
  return (
    <div className="cur">
      <div className="cur-h">
        <IconWithCheck icon={topic.icon} done={topic.done} />
        <div className="cur-t">
          <b>{topic.title_ru}</b>
          <small>{topicMeta(lessons)}</small>
        </div>
      </div>
      {lessons.map((l, i) => {
        if (l.status === 'locked') {
          return (
            <div key={l.number} className="lsn lock" aria-disabled="true">
              <span className="num">{i + 1}</span>
              <span className="t">
                <LessonTitle lesson={l} />
                <small>{wordsW(l.total)}</small>
              </span>
              <span className="tmr">
                <LockIcon />
                после {i}
              </span>
            </div>
          )
        }
        if (l.status === 'done') {
          const mine = isBusyFor(busy, l)
          return (
            <button
              key={l.number}
              type="button"
              className="lsn review"
              aria-busy={mine || undefined}
              onClick={() => onPlay(l)}
            >
              <span className="num">✓</span>
              <span className="t">
                <LessonTitle lesson={l} />
                <small>{wordsW(l.total)}</small>
              </span>
              <span className={`mini-play${mine ? ' busy' : ''}`}>{mine ? <BusyLabel /> : 'Повторить'}</span>
            </button>
          )
        }
        const shown = l.introduced > 0
        return (
          <div key={l.number} className="lsn nowp">
            <span className="num now">{i + 1}</span>
            <span className="t">
              <LessonTitle lesson={l} />
              <small>{shown ? `показано ${l.introduced} из ${l.total}` : wordsW(l.total)}</small>
            </span>
          </div>
        )
      })}
      {current && <PlayButton lesson={current} busy={busy} label="Играть" onClick={() => onPlay(current)} />}
    </div>
  )
}

export function Lessons({
  me,
  busy,
  onPlay,
  onBack,
}: {
  me: Me
  busy: Busy
  onPlay: (lesson: LessonOut) => void
  onBack: () => void
}) {
  return (
    <main className="wrap">
      {/* While a session opens, every tap but the busy button's lands here (see PlayButton). */}
      {busy && <div className="scrim" aria-hidden="true" />}
      <div className="topbar">
        <button type="button" className="x" aria-label="На главную" onClick={onBack}>
          <BackIcon />
        </button>
        <h1>Уроки</h1>
      </div>

      <div className="lhello">
        <Mascot size={64} />
        <div className="bubble">Каждый день — одна тема из каждого раздела</div>
      </div>

      {SECTIONS.map((section) => {
        const topics = me.topics.filter((t) => t.section === section.key)
        const allDone = topics.length > 0 && topics.every((t) => t.done) && !topics.some((t) => t.status === 'today')
        return (
          <section className="sec" key={section.key}>
            <div className="sech">
              <Emoji value={section.icon} alt="" />
              {section.title}
            </div>
            {allDone && (
              <div className="allnote">
                <span className="num">✓</span>
                Все {ALL_DONE_LABEL[section.key]} пройдены, можно повторить
              </div>
            )}
            <div className="rows">
              {topics.map((topic) => {
                const lessons = topicLessons(me, topic.slug)
                if (topic.status === 'locked') {
                  return <LockedRow key={topic.slug} topic={topic} lessons={lessons} />
                }
                if (topic.status === 'today') {
                  return <TodayCard key={topic.slug} topic={topic} lessons={lessons} busy={busy} onPlay={onPlay} />
                }
                return <OpenRow key={topic.slug} topic={topic} lessons={lessons} busy={busy} onPlay={onPlay} />
              })}
            </div>
          </section>
        )
      })}
    </main>
  )
}
