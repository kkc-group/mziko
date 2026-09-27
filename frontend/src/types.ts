// Mirrors backend/app/schemas/*.py. Keep field names identical to the API.

// `text`: no picture, the value (a letter or a word) is drawn as large Georgian text.
export type ImageKind = 'emoji' | 'color' | 'file' | 'text'

/** Example word for a letter card: "ბ as in ⚽ ბურთი". */
export interface AnchorOut {
  ka: string
  tr: string
  ru: string
  emoji: string | null
}

export interface WordOut {
  slug: string
  topic_slug: string
  ka: string
  tr: string
  ru: string
  image: { kind: ImageKind; value: string }
  anchor: AnchorOut | null
  audio_url: string
}

export type StepType = 'intro' | 'listen' | 'recall'

export interface Step {
  type: StepType
  word: WordOut
  options: WordOut[]
}

/** One step of the child's path: a topic, or a part of a bigger one. */
export interface LessonOut {
  number: number
  topic_slug: string
  title_ru: string
  icon: string
  part: number
  parts: number
  total: number
  introduced: number
  status: 'done' | 'current' | 'locked'
  playable: boolean
}

export interface Me {
  child: { id: number; name: string }
  settings: { rate: number; cap_lari: number; show_hint: boolean }
  week: {
    week_start: string
    today: string
    coins: number
    lari: number
    study_days: string[]
  }
  lessons: LessonOut[]
  review_available: boolean
  stickers: { word: WordOut; learned: boolean }[]
}

export interface SessionOut {
  session_id: string | null
  steps: Step[]
}

export interface AnswerResult {
  correct: boolean
  coins_gained: number
  word_learned: boolean
  week_coins: number
  week_lari: number
}

export interface SessionSummary {
  session_id: string
  coins_gained: number
  learned: WordOut[]
  week_coins: number
  week_lari: number
}
