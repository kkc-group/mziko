/** Coins flying from an answer button into the jar. Pure DOM, removed when done. */
export function flyCoins(from: Element, to: Element, count: number): void {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const a = from.getBoundingClientRect()
  const b = to.getBoundingClientRect()
  const n = Math.min(count, 6)
  for (let i = 0; i < n; i++) {
    const coin = document.createElement('div')
    coin.className = 'coin'
    coin.textContent = '₾'
    coin.style.left = `${a.left + a.width / 2 - 17}px`
    coin.style.top = `${a.top + a.height / 2 - 17}px`
    document.body.appendChild(coin)
    const dx = b.left - a.left - a.width / 2 + 17
    const dy = b.top - a.top - a.height / 2 + 17
    setTimeout(() => {
      coin.style.transform = `translate(${dx}px, ${dy}px) scale(.5)`
      coin.style.opacity = '.2'
    }, 30 + i * 90)
    setTimeout(() => coin.remove(), 800 + i * 90)
  }
}

/** UUID v4 that also works on plain http (crypto.randomUUID needs a secure context). */
export function uuid(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const b = new Uint8Array(16)
  crypto.getRandomValues(b)
  b[6] = (b[6] & 0x0f) | 0x40
  b[8] = (b[8] & 0x3f) | 0x80
  const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`
}

export function fmtLari(value: number): string {
  return value.toFixed(1).replace('.', ',')
}

export function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}
