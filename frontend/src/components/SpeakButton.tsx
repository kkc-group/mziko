import { useState } from 'react'
import type { Speaker } from '../audio'
import type { WordOut } from '../types'
import { SpeakerIcon } from './Mascot'

export function SpeakButton({
  word,
  speaker,
  small = false,
  label = 'Послушать',
}: {
  word: WordOut
  speaker: Speaker
  small?: boolean
  label?: string
}) {
  const [pulse, setPulse] = useState(0)
  return (
    <button
      key={pulse}
      type="button"
      className={`speak${small ? ' sm' : ''}${pulse ? ' playing' : ''}`}
      aria-label={label}
      onClick={() => {
        setPulse((n) => n + 1)
        void speaker.play(word)
      }}
    >
      <SpeakerIcon />
    </button>
  )
}
