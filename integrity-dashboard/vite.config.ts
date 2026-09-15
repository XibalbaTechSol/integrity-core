import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { resolve } from 'node:path'
import { execFileSync } from 'node:child_process'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const cortexHome = process.env.CORTEX_HOME ?? resolve(homedir(), '.hermes/xibalba-cortex')
const cortexTokenFile = process.env.CORTEX_DEV_TOKEN_FILE ?? resolve(cortexHome, '.viewer-dev.token')

function localCortexToken(): string {
  if (existsSync(cortexTokenFile)) return readFileSync(cortexTokenFile, 'utf8').trim()
  mkdirSync(cortexHome, { recursive: true })
  const output = execFileSync(
    'uv',
    ['run', 'xibalba-cortex-ingest-tokens', '--home', cortexHome, 'issue', '--label', 'dashboard-local-dev', '--role', 'operator'],
    { cwd: resolve(import.meta.dirname, '../../xibalba-cortex'), encoding: 'utf8', stdio: ['ignore', 'pipe', 'inherit'] },
  )
  const token = output.trim().split(/\r?\n/).at(-1)?.trim() ?? ''
  if (!token) throw new Error('Cortex development token issuance returned no token')
  writeFileSync(cortexTokenFile, `${token}\n`, { mode: 0o600 })
  chmodSync(cortexTokenFile, 0o600)
  return token
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/cortex-api': {
        target: process.env.CORTEX_LOCAL_API_URL ?? 'http://127.0.0.1:8420',
        changeOrigin: false,
        rewrite: (path) => path.replace(/^\/cortex-api/, ''),
        configure: (proxy) => {
          const token = localCortexToken()
          proxy.on('proxyReq', (request) => request.setHeader('Authorization', `Bearer ${token}`))
        },
      },
      '/api/shield': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      }
    }
  }
})
