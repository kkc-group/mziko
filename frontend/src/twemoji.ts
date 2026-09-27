/** Path of the bundled Twemoji SVG for an emoji character (files come from scripts/fetch_twemoji.py). */
export function twemojiUrl(emoji: string): string {
  // Mirrors twemoji's grabTheRightIcon: drop the FE0F presentation selector unless a ZWJ is present.
  // Keep in sync with file_stem() in scripts/fetch_twemoji.py.
  const text = emoji.includes('‍') ? emoji : emoji.replace(/️/g, '')
  const stem = Array.from(text, (ch) => ch.codePointAt(0)!.toString(16)).join('-')
  return `/media/twemoji/${stem}.svg`
}
