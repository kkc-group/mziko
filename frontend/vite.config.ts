import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

const here = path.dirname(fileURLToPath(import.meta.url))

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
        res.setHeader('Content-Type', file.endsWith('.mp3') ? 'audio/mpeg' : 'application/octet-stream')
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
        // API responses are never cached; /pair/<code> must reach the app shell.
        navigateFallbackDenylist: [/^\/api\//, /^\/media\//],
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.pathname.startsWith('/media/audio/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'audio',
              expiration: { maxEntries: 300, maxAgeSeconds: 30 * 24 * 3600 },
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
