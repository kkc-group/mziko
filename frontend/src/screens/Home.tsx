import { fmtLari, plural } from '../fx'
import type { LessonOut, Me, TopicOut } from '../types'
import { Emoji } from '../components/Emoji'
import { JarIcon, Mascot } from '../components/Mascot'
import { Menu } from '../components/Menu'
import { PlayButton } from '../components/PlayButton'
import { SECTIONS } from '../sections'
import type { Busy } from '../busy'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

type Section = (typeof SECTIONS)[number]

/** A section's next step today (docs/mockups/home-today.html): a lesson to play, done for today
 *  (its next topic opens tomorrow), or finished for good. */
type SectionStep =
  | { kind: 'play'; section: Section; lesson: LessonOut }
  | { kind: 'rest'; section: Section; next: TopicOut }
  | { kind: 'finished'; section: Section; count: number }

/** Mirrors backend/app/services/lessons.py position(): the first lesson of the section that may be
 *  played today and isn't done yet. None means the section's next topic is locked, and since the
 *  topic before it is done, it waits for tomorrow (one new topic a section a day). */
function sectionStep(me: Me, section: Section): SectionStep {
  const topics = me.topics.filter((t) => t.section === section.key)
  const slugs = new Set(topics.map((t) => t.slug))
  const lessons = me.lessons.filter((l) => slugs.has(l.topic_slug))
  const next = topics.find((t) => !t.done)
  if (!next) return { kind: 'finished', section, count: lessons.reduce((n, l) => n + l.total, 0) }
  const lesson = lessons.find((l) => l.playable && l.status !== 'done')
  return lesson ? { kind: 'play', section, lesson } : { kind: 'rest', section, next }
}

function count(section: Section, n: number): string {
  return `${n} ${plural(n, ...section.unit)}`
}

/** «показано 6 из 8» once the lesson is started, else its size in the section's unit: «8 букв». */
function lessonSub(section: Section, lesson: LessonOut): string {
  return lesson.introduced > 0 ? `показано ${lesson.introduced} из ${lesson.total}` : count(section, lesson.total)
}

function LessonTitle({ lesson }: { lesson: LessonOut }) {
  return (
    <>
      {lesson.title_ru}
      {lesson.parts > 1 && <span className="part">{`\u00a0·\u00a0${lesson.part}`}</span>}
    </>
  )
}

/** The big card: the first section, in SECTIONS order, with something to play today. */
function PlayCard({
  step,
  busy,
  onPlay,
}: {
  step: Extract<SectionStep, { kind: 'play' }>
  busy: Busy
  onPlay: (lesson: LessonOut) => void
}) {
  const { section, lesson } = step
  const shown = lesson.introduced > 0
  return (
    <div className="cur">
      <div className="cur-sec">
        <Emoji value={section.icon} alt="" />
        {section.title}
      </div>
      <div className="cur-h">
        <span className="ic">
          <Emoji value={lesson.icon} alt="" />
        </span>
        <div className="cur-t">
          <b>
            <LessonTitle lesson={lesson} />
          </b>
          <small>{lessonSub(section, lesson)}</small>
        </div>
      </div>
      {shown && (
        <div className="prog">
          <i style={{ width: `${Math.round((lesson.introduced / lesson.total) * 100)}%` }} />
        </div>
      )}
      <PlayButton lesson={lesson} busy={busy} label="Играть" onClick={() => onPlay(lesson)} />
    </div>
  )
}

/** A section under the big card: a row with «Играть», or a mint row that is not a button. */
function StepRow({ step, busy, onPlay }: { step: SectionStep; busy: Busy; onPlay: (lesson: LessonOut) => void }) {
  const { section } = step
  if (step.kind === 'finished') {
    return (
      <div className="lsn ready">
        <span className="chk" aria-hidden="true">
          ★
        </span>
        <span className="t">
          {section.finished}
          <small>
            {section.title} · {count(section, step.count)}
          </small>
        </span>
      </div>
    )
  }
  if (step.kind === 'rest') {
    return (
      <div className="lsn ready">
        <span className="chk" aria-hidden="true">
          ✓
        </span>
        <span className="t">
          На сегодня готово
          <small>
            {section.title} · завтра «{step.next.title_ru}»
          </small>
        </span>
      </div>
    )
  }
  const { lesson } = step
  return (
    <div className="lsn">
      <span className="ic">
        <Emoji value={lesson.icon} alt="" />
      </span>
      <span className="t">
        <LessonTitle lesson={lesson} />
        <small>
          {section.title} · {lessonSub(section, lesson)}
        </small>
      </span>
      <PlayButton lesson={lesson} busy={busy} small label="Играть" onClick={() => onPlay(lesson)} />
    </div>
  )
}

export function Home({
  me,
  busy,
  onPlay,
  menuOpen,
  onOpenMenu,
  onCloseMenu,
  onOpenLessons,
  onOpenMap,
}: {
  me: Me
  busy: Busy
  onPlay: (lesson: LessonOut | null) => void
  /** Not used since the home screen stopped replaying done lessons (they live on «Уроки»);
   *  kept so App.tsx needs no change in this step. */
  onReplay: (lesson: LessonOut) => void
  menuOpen: boolean
  onOpenMenu: () => void
  onCloseMenu: () => void
  onOpenLessons: () => void
  onOpenMap: () => void
}) {
  const learnedTotal = me.stickers.filter((s) => s.learned).length
  const allDone = me.topics.length > 0 && me.topics.every((t) => t.done)
  const steps = SECTIONS.map((section) => sectionStep(me, section))
  const first = steps.find((s) => s.kind === 'play')

  return (
    <main className="wrap">
      {/* While a session opens, every tap but the busy button's lands here (see PlayButton). */}
      {busy && <div className="scrim" aria-hidden="true" />}
      <Menu open={menuOpen} onOpen={onOpenMenu} onClose={onCloseMenu} onLessons={onOpenLessons} onMap={onOpenMap} />

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
        {allDone ? (
          <div className="step">
            <div className="cur all">
              <Mascot size={88} />
              <b>Все уроки пройдены!</b>
              <small>{learnedTotal} слов выучено</small>
              <PlayButton
                lesson={null}
                busy={busy}
                disabled={!me.review_available}
                label={me.review_available ? 'Повторить слова' : 'Всё закреплено!'}
                onClick={() => onPlay(null)}
              />
            </div>
          </div>
        ) : (
          <>
            {/* The first section with something to play is the big card, always on top; the others
                follow as rows in SECTIONS order, «Тренировка» last. Nothing to play: the day-done card. */}
            {first?.kind === 'play' ? (
              <PlayCard step={first} busy={busy} onPlay={onPlay} />
            ) : (
              <div className="cur all">
                <Mascot size={88} />
                <b>На сегодня всё!</b>
                <small>
                  {me.review_available ? 'Новые задания — завтра. А пока можно повторить' : 'Новые задания — завтра'}
                </small>
                <PlayButton
                  lesson={null}
                  busy={busy}
                  disabled={!me.review_available}
                  label={me.review_available ? 'Повторить' : 'Всё закреплено!'}
                  onClick={() => onPlay(null)}
                />
              </div>
            )}
            {steps
              .filter((s) => s !== first)
              .map((s) => (
                <StepRow key={s.section.key} step={s} busy={busy} onPlay={onPlay} />
              ))}
            {first && me.review_available && (
              <div className="lsn">
                <span className="ic">
                  <Emoji value="🔁" alt="" />
                </span>
                <span className="t">
                  Тренировка
                  <small>Повторим знакомое</small>
                </span>
                <PlayButton lesson={null} busy={busy} small label="Повторить" onClick={() => onPlay(null)} />
              </div>
            )}
            <button type="button" className="lsn nav" onClick={onOpenLessons}>
              <span className="ic">
                <Emoji value="📚" alt="" />
              </span>
              <span className="t">Другие уроки</span>
              <span className="chev">▸</span>
            </button>
          </>
        )}
      </div>
    </main>
  )
}
