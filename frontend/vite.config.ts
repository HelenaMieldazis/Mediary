import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'bg-medical-1.png', 'bg-medical-2.png'],
      manifest: {
        name: 'Mediary - Diário de Sintomas',
        short_name: 'Mediary',
        description: 'Registre e acompanhe seus sintomas de saúde',
        theme_color: '#21A9BC',
        background_color: '#21A9BC',
        display: 'standalone',
        orientation: 'portrait',
        scope: '/',
        start_url: '/',
        icons: [
          {
            src: 'icon-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: 'icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any'
          },
          {
            src: 'icon-maskable-192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'maskable'
          },
          {
            src: 'icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable'
          }
        ]
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webp,woff2}'],
        // Respostas da API (/api/*) contêm dados de saúde e NUNCA devem ir
        // para o Cache Storage: não há regra de runtimeCaching para elas,
        // então o service worker não intercepta essas requisições.
        // Também impede que uma navegação direta para /api/* receba o
        // index.html do fallback de SPA.
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
})
