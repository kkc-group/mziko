import type { CSSProperties } from 'react'
import type { WordOut } from '../types'

/** Emoji, colour blob or picture for a word. Size comes from the parent via --s. */
export function WordImage({ word }: { word: WordOut }) {
  const { kind, value } = word.image
  if (kind === 'color') {
    return <span className="blob" style={{ '--c': value } as CSSProperties} role="img" aria-label={word.ru} />
  }
  if (kind === 'file') {
    return <img className="pic-img" src={value} alt={word.ru} />
  }
  return (
    <span className="emoji" role="img" aria-label={word.ru}>
      {value}
    </span>
  )
}
