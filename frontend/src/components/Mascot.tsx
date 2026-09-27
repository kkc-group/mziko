export function Mascot({ bounce = 0, size = 120 }: { bounce?: number; size?: number }) {
  return (
    <svg
      key={bounce}
      className={`mascot${bounce ? ' bounce' : ''}`}
      style={{ width: size, height: size }}
      viewBox="0 0 120 120"
      aria-label="Мзико"
    >
      <g fill="var(--sun)" stroke="var(--sun-dark)" strokeWidth="3">
        <path d="M60 4 L66 20 L54 20Z" />
        <path d="M60 116 L66 100 L54 100Z" />
        <path d="M4 60 L20 54 L20 66Z" />
        <path d="M116 60 L100 54 L100 66Z" />
        <path d="M20 20 L34 28 L28 34Z" />
        <path d="M100 100 L86 92 L92 86Z" />
        <path d="M100 20 L92 34 L86 28Z" />
        <path d="M20 100 L28 86 L34 92Z" />
        <circle cx="60" cy="60" r="36" />
      </g>
      <circle cx="47" cy="55" r="5" fill="#3a2600" />
      <circle cx="73" cy="55" r="5" fill="#3a2600" />
      <circle cx="49" cy="53" r="1.6" fill="#fff" />
      <circle cx="75" cy="53" r="1.6" fill="#fff" />
      <circle cx="40" cy="67" r="5" fill="#FF8E8E" opacity=".7" />
      <circle cx="80" cy="67" r="5" fill="#FF8E8E" opacity=".7" />
      <path d="M48 70 Q60 82 72 70" fill="none" stroke="#3a2600" strokeWidth="4" strokeLinecap="round" />
    </svg>
  )
}

export function JarIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" aria-hidden="true">
      <path d="M18 14 H46 L44 20 Q56 30 52 48 Q48 60 32 60 Q16 60 12 48 Q8 30 20 20Z" fill="#C8683E" />
      <path d="M18 14 H46 L44 20 H20Z" fill="#A4532F" />
      <path d="M14 38 Q32 44 50 38" stroke="#E7A07A" strokeWidth="3" fill="none" />
      <circle cx="32" cy="10" r="6" fill="var(--sun)" stroke="var(--sun-dark)" strokeWidth="2" />
    </svg>
  )
}

export function SpeakerIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M4 9h4l5-4v14l-5-4H4z" fill="#4a3200" />
      <path
        d="M16 8.5a5 5 0 010 7M18.5 6a8.5 8.5 0 010 12"
        stroke="#4a3200"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function Hills() {
  return (
    <svg className="hills" viewBox="0 0 540 140" preserveAspectRatio="none" aria-hidden="true">
      <path d="M0 90 Q120 20 260 80 T540 60 V140 H0Z" fill="var(--hill1)" />
      <path d="M0 120 Q160 70 320 110 T540 100 V140 H0Z" fill="var(--hill2)" />
    </svg>
  )
}
