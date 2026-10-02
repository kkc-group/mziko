import type { TopicOut } from './types'

/** The three sections of the programme, in the order the «Уроки» and «Карта прогресса» screens show them.
 *  `unit` is the section's counting word (1 буква, 2 буквы, 5 букв), `finished` the home row once
 *  every topic of the section is done (docs/mockups/home-today.html). */
export const SECTIONS: {
  key: TopicOut['section']
  title: string
  icon: string
  unit: [string, string, string]
  finished: string
}[] = [
  { key: 'letters', title: 'Буквы', icon: '🔤', unit: ['буква', 'буквы', 'букв'], finished: 'Все буквы пройдены!' },
  { key: 'syllables', title: 'Слоги', icon: '🧩', unit: ['слог', 'слога', 'слогов'], finished: 'Все слоги пройдены!' },
  { key: 'words', title: 'Слова', icon: '💬', unit: ['слово', 'слова', 'слов'], finished: 'Все слова пройдены!' },
]

/** Why a topic is locked: a parent closed it in the cabinet, the previous topic of its section
 *  isn't done yet, or the section already opened a new topic today and this one waits for
 *  tomorrow (mirrors the locked reasons of `position` in backend/app/services/lessons.py).
 *  `topics` is `me.topics`, whose order within a section is the order this reads the "previous"
 *  one from; a closed topic is out of the queue, so the one before it is the previous. */
export function lockedReason(topics: TopicOut[], topic: TopicOut): string {
  if (topic.closed) return 'закрыли родители'
  const siblings = topics.filter((t) => t.section === topic.section && !t.closed)
  const i = siblings.findIndex((t) => t.slug === topic.slug)
  const previous = i > 0 ? siblings[i - 1] : null
  return previous && !previous.done ? `после «${previous.title_ru}»` : 'завтра'
}
