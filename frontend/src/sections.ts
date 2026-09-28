import type { TopicOut } from './types'

/** The three sections of the programme, in the order the «Уроки» and «Карта прогресса» screens show them. */
export const SECTIONS: { key: TopicOut['section']; title: string; icon: string }[] = [
  { key: 'letters', title: 'Буквы', icon: '🔤' },
  { key: 'syllables', title: 'Слоги', icon: '🧩' },
  { key: 'words', title: 'Слова', icon: '💬' },
]
