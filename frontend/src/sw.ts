import { registerSW } from 'virtual:pwa-register'

let registered = false

// A new build takes over as soon as its service worker is active: the page
// reloads itself (the injected default script never did). A home-screen app
// can stay open for days, so it also asks for updates once an hour.
//
// Called from App once the home (or error) screen is shown rather than at
// startup, so registration doesn't compete with the login/me requests;
// idempotent because that call happens on every later screen change.
export function registerAppServiceWorker(): void {
  if (registered) return
  registered = true
  registerSW({
    immediate: true,
    onRegisteredSW(_url, registration) {
      if (registration) setInterval(() => void registration.update(), 60 * 60 * 1000)
    },
  })
}
