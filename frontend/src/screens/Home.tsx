import { fmtLari } from '../fx'
import type { Me, TopicOut } from '../types'
import { JarIcon, Mascot } from '../components/Mascot'
import { WordImage } from '../components/WordImage'

const DAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export function Home({
  me,
  busy,
  onPlay,
}: {
  me: Me
  busy: boolean
  onPlay: (topic: TopicOut) => void
}) {
  const learnedTotal = me.stickers.filter((s) => s.learned).length
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

      <div className="topics">
        {me.topics.map((t) => (
          <button
            key={t.slug}
            type="button"
            className="topic"
            disabled={busy || !t.has_lesson}
            onClick={() => onPlay(t)}
          >
            <span className="ic">{t.icon}</span>
            <span>
              <b>{t.title_ru}</b>
              <span>
                {t.has_lesson ? `выучено ${t.learned} из ${t.total}` : 'На сегодня всё! Завтра новые слова'}
              </span>
            </span>
          </button>
        ))}
      </div>

      <div className="learned">
        Наклейки: {learnedTotal} из {me.stickers.length}
      </div>
      <div className="stickers">
        {me.stickers.map((s) => (
          <div
            key={`${s.word.topic_slug}/${s.word.slug}`}
            className={`stk${s.learned ? '' : ' lock'}`}
            title={s.word.ru}
          >
            <WordImage word={s.word} />
          </div>
        ))}
      </div>
    </main>
  )
}
