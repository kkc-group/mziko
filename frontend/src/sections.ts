import type { TopicOut } from './types'

/** The three sections of the programme, in the order the «Уроки» and «Карта прогресса» screens show them. */
export const SECTIONS: { key: TopicOut['section']; title: string; icon: string }[] = [
  { key: 'letters', title: 'Буквы', icon: '🔤' },
  { key: 'syllables', title: 'Слоги', icon: '🧩' },
  { key: 'words', title: 'Слова', icon: '💬' },
]

/** Why a not-yet-started topic is locked: the previous topic of its section isn't done yet, or the
 *  section already opened a new topic today and this one waits for tomorrow (mirrors the two
 *  locked reasons in backend/app/services/lessons.py:198-200). `topics` is `me.topics`, whose
 *  order within a section is the order this reads the "previous" one from. */
export function lockedReason(topics: TopicOut[], topic: TopicOut): string {
  const siblings = topics.filter((t) => t.section === topic.section)
  const i = siblings.findIndex((t) => t.slug === topic.slug)
  const previous = i > 0 ? siblings[i - 1] : null
  return previous && !previous.done ? `после «${previous.title_ru}»` : 'завтра'
}
