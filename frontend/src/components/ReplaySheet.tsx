import type { LessonOut, TopicOut } from '../types'
import { Emoji } from './Emoji'
import { CrossIcon } from './Icons'

/** The bottom sheet under every «Повторить»: quiz the lesson again, or start its whole topic over.
 *  Mockup: docs/mockups/lesson-restart.html. */
export function ReplaySheet({
  lesson,
  topic,
  busy,
  onClose,
  onQuiz,
  onRestart,
}: {
  lesson: LessonOut
  topic: TopicOut
  busy: boolean
  onClose: () => void
  onQuiz: (lesson: LessonOut) => void
  onRestart: (topic: TopicOut) => void
}) {
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="sheet bottom" role="dialog" aria-label="Как повторим?">
        <div className="cur-h">
          <span className="ic">
            <Emoji value={topic.icon} alt="" />
          </span>
          <div className="cur-t">
            <b>{topic.title_ru}</b>
            <small>Как повторим?</small>
          </div>
          <button type="button" className="x" aria-label="Закрыть" onClick={onClose}>
            <CrossIcon />
          </button>
        </div>
        <button type="button" className="mi on" disabled={busy} onClick={() => onQuiz(lesson)}>
          <Emoji value="🎯" alt="" />
          <span className="t">
            Повторить слова
            <small>Викторина по словам этого урока и парочке старых</small>
          </span>
        </button>
        <button type="button" className="mi on" disabled={busy} onClick={() => onRestart(topic)}>
          <Emoji value="🔄" alt="" />
          <span className="t">
            Пройти тему с начала
            <small>Все уроки темы заново, по три слова за раз. Монеты и наклейки останутся</small>
          </span>
        </button>
      </div>
    </>
  )
}
