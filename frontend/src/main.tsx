import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './styles.css'

// A new build takes over as soon as its service worker is active: the page
// reloads itself (the injected default script never did). A home-screen app
// can stay open for days, so it also asks for updates once an hour.
registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    if (registration) setInterval(() => void registration.update(), 60 * 60 * 1000)
  },
})

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
