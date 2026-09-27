import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import type { Plugin } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';
import { defineConfig } from 'vitest/config';

// Values mirror the design tokens in src/styles/tokens.css (a manifest cannot reference CSS).
const BACKGROUND_COLOR = '#ffffff';
const THEME_COLOR = '#2e7d32';

/** Hosts the build must never refer to: everything is served by the app itself (SEC-08). */
const CDN_HOSTS = ['cdn.jsdelivr.net', 'fastly.jsdelivr.net', 'unpkg.com'];
const ZXING_SHARE = /[\\/]zxing-wasm[\\/]dist[\\/]es[\\/]share\.js$/;
const ZXING_DEFAULT_CDN = /https:\/\/fastly\.jsdelivr\.net\/npm\/zxing-wasm@[^/]+\/dist\//;

/**
 * zxing-wasm's default `locateFile` loads the decoder's wasm from a CDN. The app always replaces
 * it with the wasm file from its own build (features/scanner/decoder.ts), and the CSP would block
 * the CDN anyway; this plugin also removes the URL from the bundle, and fails the build if any
 * chunk still names a CDN (e.g. after a zxing-wasm update changed that code).
 */
function selfHostedDecoder(): Plugin {
  return {
    name: 'mealmate:self-hosted-decoder',
    transform(code, id) {
      if (!ZXING_SHARE.test(id)) return null;
      // What's left is a relative path on the app's own origin, which is never used.
      return { code: code.replace(ZXING_DEFAULT_CDN, ''), map: null };
    },
    generateBundle(_options, bundle) {
      for (const [fileName, output] of Object.entries(bundle)) {
        const text = output.type === 'chunk' ? output.code : '';
        const host = CDN_HOSTS.find((name) => text.includes(name));
        if (host) this.error(`${fileName} refers to ${host}; the app must serve everything itself`);
      }
    },
  };
}

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    selfHostedDecoder(),
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
