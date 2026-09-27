// Helpers for text cards (image.kind = 'text'): a letter or a word shown instead of a picture.
import type { WordOut } from './types'

/** True for cards without a picture: the Georgian text itself is shown instead. */
export function isText(word: WordOut): boolean {
  return word.image.kind === 'text'
}

/** A text card holding a single letter (as opposed to a whole word). */
export function isLetter(word: WordOut): boolean {
  return isText(word) && [...word.image.value].length === 1
}

/** Class suffix for containers (.pic, .tile, .stk) that must grow to fit a text word. */
export function textClass(word: WordOut): string {
  return isText(word) && !isLetter(word) ? ' txt' : ''
}
