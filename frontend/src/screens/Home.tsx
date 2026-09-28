import { fmtLari, wordsW } from '../fx'
import type { LessonOut, Me } from '../types'
import { Emoji } from '../components/Emoji'
import { JarIcon, Mascot } from '../components/Mascot'
import { Menu } from '../components/Menu'
import { PlayButton } from '../components/PlayButton'
import type { Busy } from '../busy'
import { WordImage } from '../components/WordImage'
import { textClass } from '../wordText'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

function LessonTitle({ lesson }: { lesson: LessonOut }) {
  return (
    <>
      {lesson.title_ru}
      {lesson.parts > 1 && <span className="part"> · {lesson.part}</span>}
    </>
  )
}

/** Today's topic card: review rows for its already-played parts, progress, then the play button. */
function TodayLessonCard({
  lesson,
  lessons,
  busy,
  onPlay,
}: {
  lesson: LessonOut
  lessons: LessonOut[]
  busy: Busy
  onPlay: (lesson: LessonOut) => void
}) {
  const doneSiblings = lessons.filter((l) => l.topic_slug === lesson.topic_slug && l.part < lesson.part)
  const finished = lesson.status === 'done'
  const shown = lesson.introduced > 0
  const sub = finished
    ? `показано ${lesson.total} из ${lesson.total}`
    : shown
      ? `показано ${lesson.introduced} из ${lesson.total}`
      : wordsW(lesson.total)
  const pct = finished ? 100 : Math.round((lesson.introduced / lesson.total) * 100)

  return (
    <div className="cur">
      <div className="cur-h">
        <span className="num now">{lesson.number}</span>
        <span className="ic">
          <Emoji value={lesson.icon} alt="" />
        </span>
        <div className="cur-t">
          <b>
            <LessonTitle lesson={lesson} />
          </b>
          <small>{sub}</small>
        </div>
      </div>
      {(shown || finished) && (
        <div className="prog">
          <i style={{ width: `${pct}%` }} />
        </div>
      )}
      {doneSiblings.map((l) => (
        <div key={l.number} className="lsn review">
          <span className="num">✓</span>
          <span className="t">
            <LessonTitle lesson={l} />
            <small>{wordsW(l.total)}</small>
          </span>
          <PlayButton lesson={l} busy={busy} small label="Повторить" onClick={() => onPlay(l)} />
        </div>
      ))}
      <PlayButton
        lesson={lesson}
        busy={busy}
        label={finished ? 'Повторить' : 'Играть'}
        onClick={() => onPlay(lesson)}
      />
      {finished && <p className="soon">Новый урок — завтра</p>}
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
}: {
  me: Me
  busy: Busy
  onPlay: (lesson: LessonOut | null) => void
  menuOpen: boolean
  onOpenMenu: () => void
  onCloseMenu: () => void
  onOpenLessons: () => void
}) {
  const learnedTotal = me.stickers.filter((s) => s.learned).length
  const lesson = me.today_lesson != null ? (me.lessons.find((l) => l.number === me.today_lesson) ?? null) : null
  const allDone = me.topics.length > 0 && me.topics.every((t) => t.done)

  return (
    <main className="wrap">
      {/* While a session opens, every tap but the busy button's lands here (see PlayButton). */}
      {busy && <div className="scrim" aria-hidden="true" />}
      <Menu open={menuOpen} onOpen={onOpenMenu} onClose={onCloseMenu} onLessons={onOpenLessons} />

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
        {lesson ? (
          <>
            <div className="step">
              <TodayLessonCard lesson={lesson} lessons={me.lessons} busy={busy} onPlay={onPlay} />
            </div>
            <div className="step">
              <button type="button" className="lsn nav" onClick={onOpenLessons}>
                <span className="ic">
                  <Emoji value="📚" alt="" />
                </span>
                <span className="t">Другие уроки</span>
                <span className="chev">▸</span>
              </button>
            </div>
          </>
        ) : allDone ? (
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
          <div className="step">
            <div className="cur all">
              <Mascot size={88} />
              <b>Выбери урок на сегодня</b>
              <small>Каждый день — одна тема из каждого раздела</small>
              <button type="button" className="play" onClick={onOpenLessons}>
                К урокам
              </button>
            </div>
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
