import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vitest/config';

// Values mirror the design tokens in src/styles/tokens.css (a manifest cannot reference CSS).
const BACKGROUND_COLOR = '#ffffff';
const THEME_COLOR = '#2e7d32';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      strategies: 'injectManifest',
      srcDir: 'src/sw',
      filename: 'sw.ts',
      registerType: 'prompt',
      // Registration happens in src/main.tsx; an injected inline script would violate the CSP.
      injectRegister: null,
      // Precache the whole build output; the plugin adds the web manifest itself.
      injectManifest: {
        globPatterns: ['**/*.{js,css,html,svg,png}'],
      },
      includeManifestIcons: false,
      manifest: {
        id: '/',
        name: 'MealMate',
        short_name: 'MealMate',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        background_color: BACKGROUND_COLOR,
        theme_color: THEME_COLOR,
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-maskable-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8080',
    },
  },
  build: {
    outDir: 'dist',
    rolldownOptions: {
      output: {
        // The framework changes less often than the app: a separate chunk keeps the main chunk
        // small and lets an app update reuse the cached framework code.
        codeSplitting: {
          groups: [
            {
              name: 'react',
              test: /[\\/]node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/,
            },
          ],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
    unstubGlobals: true,
  },
});
