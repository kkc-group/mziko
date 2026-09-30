import type { View } from '../App'
import { Emoji } from './Emoji'

const TABS: { view: View; icon: string; label: string }[] = [
  { view: 'home', icon: '☀️', label: 'Сегодня' },
  { view: 'lessons', icon: '🧭', label: 'Путь' },
  { view: 'map', icon: '🗺️', label: 'Наклейки' },
]

/** Bottom navigation between «Сегодня», «Путь» and «Наклейки» (docs/mockups/home-today.html,
 *  "Нижние вкладки — вблизи"). Mounted once in App.tsx as a fixed sibling of .wrap, like <Hills/>,
 *  so it stays put while the screen under it scrolls or switches.
 *
 *  `busy` (a session opening) dims and disables the tabs directly, instead of relying on the
 *  session's own .scrim: that scrim is rendered inside the screen's .wrap, which is its own
 *  stacking context (styles.css:62), so it cannot reach a sibling mounted outside it — see the
 *  z-index note by .tabs in styles.css. */
export function Tabs({ view, onSelect, busy }: { view: View; onSelect: (view: View) => void; busy: boolean }) {
  return (
    <nav className="tabs" aria-label="Разделы">
      {TABS.map((t) => (
        <button
          key={t.view}
          type="button"
          className={`tab${t.view === view ? ' on' : ''}`}
          aria-current={t.view === view ? 'page' : undefined}
          disabled={busy}
          onClick={() => onSelect(t.view)}
        >
          <Emoji value={t.icon} alt="" />
          {t.label}
        </button>
      ))}
    </nav>
  )
}
