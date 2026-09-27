import type { CSSProperties } from 'react'
import type { WordOut } from '../types'
import { isLetter } from '../wordText'
import { Emoji } from './Emoji'

/** Emoji, colour blob, picture or large text for a word. Size comes from the parent via --s. */
export function WordImage({ word }: { word: WordOut }) {
  const { kind, value } = word.image
  if (kind === 'color') {
    return <span className="blob" style={{ '--c': value } as CSSProperties} role="img" aria-label={word.ru} />
  }
  if (kind === 'file') {
    return <img className="pic-img" src={value} alt={word.ru} />
  }
  if (kind === 'text') {
    return (
      <span className={`glyph ${isLetter(word) ? 'l' : 'w'} ka`} role="img" aria-label={word.ru}>
        {value}
      </span>
    )
  }
  return <Emoji value={value} alt={word.ru} />
}
