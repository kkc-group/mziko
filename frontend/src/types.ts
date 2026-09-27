// Mirrors backend/app/schemas/*.py. Keep field names identical to the API.

export type ImageKind = 'emoji' | 'color' | 'file'

export interface WordOut {
  slug: string
  topic_slug: string
  ka: string
  tr: string
  ru: string
  image: { kind: ImageKind; value: string }
  audio_url: string
}

export type StepType = 'intro' | 'listen' | 'recall'

export interface Step {
  type: StepType
  word: WordOut
  options: WordOut[]
}

export interface TopicOut {
  slug: string
  title_ru: string
  title_ka: string
  icon: string
  total: number
  learned: number
  has_lesson: boolean
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
  topics: TopicOut[]
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
