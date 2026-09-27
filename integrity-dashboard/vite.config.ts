import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { resolve } from 'node:path'
import { defineConfig, type ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'

// Same-origin proxies for the local Shield backend and Cortex API. The bearer
// tokens are read here, on the Node side, and attached to proxied requests only:
// they are never compiled into the browser bundle (VITE_* values are). Both the
// dev server and `vite preview` (the managed integrity-dashboard.service) use
// these, and both bind to loopback.
//
// Token files are the ones those services already use locally; override with
// DASHBOARD_SHIELD_TOKEN_FILE / DASHBOARD_CORTEX_TOKEN_FILE. A missing file
// leaves the request unauthenticated, so the page shows its honest
// "API unavailable" state instead of failing to start.
const shieldTokenFile =
  process.env.DASHBOARD_SHIELD_TOKEN_FILE ?? resolve(homedir(), '.xibalba-shield/backend-admin.token')
const cortexTokenFile =
  process.env.DASHBOARD_CORTEX_TOKEN_FILE ?? resolve(homedir(), '.hermes/xibalba-cortex/.viewer-dev.token')

function readToken(path: string): string {
  return existsSync(path) ? readFileSync(path, 'utf8').trim() : ''
}

function withBearer(target: string, tokenFile: string, extra: ProxyOptions = {}): ProxyOptions {
  const token = readToken(tokenFile)
  return {
    target,
    ...extra,
    configure: (proxy) => {
      proxy.on('proxyReq', (request) => {
        // Replace, never forward, whatever Authorization the browser sent.
        request.removeHeader('Authorization')
        if (token) request.setHeader('Authorization', `Bearer ${token}`)
      })
    },
  }
}

const proxy: Record<string, ProxyOptions> = {
  // Canonical Shield control plane (retired 8421/8765 must not be revived).
  '/api/shield': withBearer('http://127.0.0.1:8435', shieldTokenFile, { changeOrigin: true }),
  // Root Cortex local API (all agent profiles mounted read-only).
  '/cortex-api': withBearer('http://127.0.0.1:8420', cortexTokenFile, {
    changeOrigin: false,
    rewrite: (path) => path.replace(/^\/cortex-api/, ''),
  }),
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: { proxy },
  preview: { proxy },
})
