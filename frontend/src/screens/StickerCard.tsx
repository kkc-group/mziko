import type { CSSProperties } from 'react'
import type { Speaker } from '../audio'
import type { WordOut } from '../types'
import { BackIcon } from '../components/Icons'
import { Hills } from '../components/Mascot'
import { SpeakButton } from '../components/SpeakButton'
import { WordImage } from '../components/WordImage'
import { isText, textClass } from '../wordText'
import { Anchor } from './Lesson'

/** A learned sticker tapped on the progress map, opened already speaking (see App.tsx): the word
 *  alone, nothing to answer, only «Послушать» to hear it again. The back arrow returns to the map. */
export function StickerCard({
  word,
  speaker,
  showHint,
  onBack,
}: {
  word: WordOut
  speaker: Speaker
  showHint: boolean
  onBack: () => void
}) {
  return (
    <div className="sticker" role="dialog" aria-label="Наклейка">
      {/* The layer covers the app's hills; the mockup keeps them on this page, so draw them again. */}
      <Hills />
      <main className="wrap">
        <div className="topbar">
          <button
            type="button"
            className="x"
            aria-label="К карте прогресса"
            onClick={() => {
              speaker.stop()
              onBack()
            }}
          >
            <BackIcon />
          </button>
          <h1>Наклейка</h1>
        </div>
        <div className="stkp">
          <div className={`pic${textClass(word)}`}>
            <WordImage word={word} />
          </div>
          {(!isText(word) || showHint) && (
            <div className="word">
              {!isText(word) && (
                <span className="ka" style={{ '--len': [...word.ka].length } as CSSProperties}>
                  {word.ka}
                </span>
              )}
              {showHint && <span className="tr">{word.tr}</span>}
            </div>
          )}
          <p className="ru">{word.ru}</p>
          {word.anchor && <Anchor letter={word.image.value} anchor={word.anchor} showHint={showHint} />}
          <SpeakButton word={word} speaker={speaker} />
        </div>
      </main>
    </div>
  )
}
