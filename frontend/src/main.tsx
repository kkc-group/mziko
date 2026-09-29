import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './styles.css'

// Service worker registration lives in ./sw and is triggered by App once the
// first screen is shown (see App.tsx), not here at startup.

// iOS Safari shows a button's :active state on touch only when some touchstart
// listener exists; the press look in styles.css depends on it.
document.addEventListener('touchstart', () => {}, { passive: true })

// A short buzz for a live button where the device can (Android); iOS has no
// vibration API, the press look does the job there.
document.addEventListener('pointerdown', (e) => {
  const button = e.target instanceof Element ? e.target.closest('button') : null
  if (button && !button.disabled && 'vibrate' in navigator) navigator.vibrate(8)
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
