import type { WordOut } from './types'

const key = (w: WordOut) => `${w.topic_slug}/${w.slug}`

/** Plays word audio from /media, falling back to speech synthesis when a file is missing. */
export class Speaker {
  private cache = new Map<string, HTMLAudioElement>()
  private missing = new Set<string>()
  private unlocked = false

  /** Create and start loading elements for every word of the session. */
  preload(words: WordOut[]): void {
    for (const w of words) {
      const k = key(w)
      if (this.cache.has(k)) continue
      const audio = new Audio(w.audio_url)
      audio.preload = 'auto'
      audio.addEventListener('error', () => this.missing.add(k))
      this.cache.set(k, audio)
    }
  }

  /**
   * iOS allows programmatic playback only for elements that were once played
   * from a user gesture. Call this inside the tap that starts the lesson.
   */
  unlock(): void {
    if (this.unlocked) return
    this.unlocked = true
    for (const audio of this.cache.values()) {
      audio.muted = true
      audio
        .play()
        .then(() => {
          audio.pause()
          audio.currentTime = 0
        })
        .catch(() => {})
        .finally(() => {
          audio.muted = false
        })
    }
  }

  async play(word: WordOut): Promise<void> {
    this.stop()
    const audio = this.cache.get(key(word))
    if (audio && !this.missing.has(key(word))) {
      try {
        audio.currentTime = 0
        await audio.play()
        return
      } catch {
        /* fall through to synthesis */
      }
    }
    speak(word)
  }

  stop(): void {
    for (const audio of this.cache.values()) {
      if (!audio.paused) audio.pause()
    }
    try {
      speechSynthesis.cancel()
    } catch {
      /* no synthesis */
    }
  }
}

let voices: SpeechSynthesisVoice[] = []
function loadVoices() {
  try {
    voices = speechSynthesis.getVoices() ?? []
  } catch {
    voices = []
  }
}
try {
  loadVoices()
  speechSynthesis.addEventListener('voiceschanged', loadVoices)
} catch {
  /* no speechSynthesis in this browser */
}

function speak(word: WordOut): void {
  try {
    const ka = voices.find((v) => v.lang.toLowerCase().startsWith('ka'))
    const utterance = new SpeechSynthesisUtterance(ka ? word.ka : word.tr)
    if (ka) {
      utterance.voice = ka
      utterance.lang = ka.lang
    } else {
      const ru = voices.find((v) => v.lang.toLowerCase().startsWith('ru'))
      if (ru) utterance.voice = ru
      utterance.lang = ru?.lang ?? 'ru-RU'
    }
    utterance.rate = 0.75
    speechSynthesis.speak(utterance)
  } catch {
    /* nothing to fall back to */
  }
}
