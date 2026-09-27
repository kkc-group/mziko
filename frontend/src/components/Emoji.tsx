import { useState } from 'react'
import { twemojiUrl } from '../twemoji'

/** An emoji drawn from the bundled Twemoji set so every device shows the same picture.
 *  Falls back to the system emoji font when the file is missing. Size comes from the parent via --s. */
export function Emoji({ value, alt }: { value: string; alt: string }) {
  const [failed, setFailed] = useState<string | null>(null)
  if (failed === value) {
    return (
      <span className="emoji" role="img" aria-label={alt}>
        {value}
      </span>
    )
  }
  return <img className="pic-img" src={twemojiUrl(value)} alt={alt} onError={() => setFailed(value)} />
}
