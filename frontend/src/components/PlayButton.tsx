import { useEffect, useState } from 'react'
import { isBusyFor, type Busy } from '../busy'
import type { LessonOut } from '../types'

/** Spinner and label inside the tapped button; after 3 s the label reassures instead. */
export function BusyLabel() {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 3000)
    return () => clearTimeout(t)
  }, [])
  return (
    <>
      <span className="spin" />
      {slow ? 'Ещё чуть-чуть…' : 'Открываю…'}
    </>
  )
}

/**
 * "Играть" / "Повторить" (docs/mockups/button-feedback.html): the tapped one stays pressed
 * with a spinner while the session opens; the screen's scrim takes every other tap.
 */
export function PlayButton({
  lesson,
  busy,
  label,
  onClick,
  small = false,
  disabled = false,
}: {
  lesson: LessonOut | null
  busy: Busy
  label: string
  onClick: () => void
  small?: boolean
  disabled?: boolean
}) {
  const mine = isBusyFor(busy, lesson)
  return (
    <button
      type="button"
      className={`${small ? 'mini-play' : 'play'}${mine ? ' busy' : ''}`}
      disabled={disabled}
      aria-busy={mine || undefined}
      onClick={onClick}
    >
      {mine ? <BusyLabel /> : label}
    </button>
  )
}
