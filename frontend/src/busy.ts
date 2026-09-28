import type { LessonOut } from './types'

/** Which play button is waiting for the server: a lesson, or `null` for "review all". */
export type Busy = { lesson: LessonOut | null } | null

export function isBusyFor(busy: Busy, lesson: LessonOut | null): boolean {
  return busy !== null && (busy.lesson?.number ?? null) === (lesson?.number ?? null)
}
