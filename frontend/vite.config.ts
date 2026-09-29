import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const here = path.dirname(fileURLToPath(import.meta.url))

const MEDIA_TYPES: Record<string, string> = {
  '.mp3': 'audio/mpeg',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
}

/** In development serve ../media the way Caddy does in production. */
function mediaDevServer(): Plugin {
  const root = path.resolve(here, '../media')
  return {
    name: 'mziko-media-dev',
    configureServer(server) {
      server.middlewares.use('/media', (req, res, next) => {
        const file = path.join(root, decodeURIComponent(req.url ?? ''))
        if (!file.startsWith(root) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
          next()
          return
        }
        res.setHeader('Content-Type', MEDIA_TYPES[path.extname(file)] ?? 'application/octet-stream')
        fs.createReadStream(file).pipe(res)
      })
    },
  }
}

export default defineConfig({
  plugins: [
    react(),
    mediaDevServer(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/mascot.svg', 'icons/icon-192.png', 'icons/icon-512.png'],
      manifest: {
        name: 'Мзико — грузинские слова',
        short_name: 'Мзико',
        lang: 'ru',
        description: 'Грузинские слова для детей: карточки, звук, монеты',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        orientation: 'any',
        background_color: '#E4F1FF',
        theme_color: '#5B2E8C',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        // API responses are never cached; /c/<code> must reach the app shell.
        // /about is the parents' landing page and /admin the owner's back office, both
        // served by Caddy, not routes of the app.
        navigateFallbackDenylist: [/^\/api\//, /^\/media\//, /^\/about(\/|$)/, /^\/admin(\/|$)/],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/media/audio/'),
            handler: 'CacheFirst',
            options: {
              // Bump when files are regenerated under the same names: CacheFirst
              // would otherwise serve the old recording for up to 30 days.
              cacheName: 'audio-v4',
              expiration: { maxEntries: 300, maxAgeSeconds: 30 * 24 * 3600 },
            },
          },
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/media/twemoji/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'twemoji',
              expiration: { maxEntries: 400, maxAgeSeconds: 30 * 24 * 3600 },
            },
          },
          {
            // Word pictures from files (image.kind: file), same lifetime as Twemoji.
            urlPattern: ({ url }) => url.pathname.startsWith('/media/images/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'images',
              expiration: { maxEntries: 400, maxAgeSeconds: 30 * 24 * 3600 },
            },
          },
          {
            urlPattern: ({ url }) => url.origin === 'https://fonts.gstatic.com',
            handler: 'CacheFirst',
            options: { cacheName: 'fonts', expiration: { maxEntries: 20, maxAgeSeconds: 365 * 24 * 3600 } },
          },
        ],
      },
    }),
  ],
  server: {
    // API_URL lets you point the dev server at a backend on another port.
    proxy: { '/api': process.env.API_URL ?? 'http://localhost:8000' },
  },
})
