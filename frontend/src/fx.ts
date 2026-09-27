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

export function fmtLari(value: number): string {
  return value.toFixed(1).replace('.', ',')
}

export function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${d}.${m}`
}
