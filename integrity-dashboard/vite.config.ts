/// <reference types="vitest" />
import { defineConfig } from 'vitest/config'
import type { Plugin, ViteDevServer } from 'vite'
import react from '@vitejs/plugin-react'
import { exec } from 'child_process'
import path from 'path'
import type { IncomingMessage, ServerResponse } from 'http'

const demoPlugin = (): Plugin => ({
  name: 'run-demo-plugin',
  configureServer(server: ViteDevServer) {
    server.middlewares.use('/integrity/__/run-demo', (req: IncomingMessage, res: ServerResponse) => {
      if (req.method !== 'POST') {
        res.statusCode = 405;
        res.end('Method Not Allowed');
        return;
      }
      
      const rootDir = path.resolve(__dirname, '..');
      
      console.log('Running make demo in', rootDir);
      const env = {
        ...process.env,
        RPC_URL: 'http://localhost:8545',
        CHAIN_ID: '31337',
        DEPLOYMENTS_FILE: path.resolve(rootDir, 'deployments.local.json'),
        FUNDER_PRIVATE_KEY: '0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80',
        INTEGRITY_WALLET_PASSWORD: 'xibalba-dev-2026'
      };
      const child = exec('make demo', { cwd: rootDir, env });
      
      child.stdout?.pipe(process.stdout);
      child.stderr?.pipe(process.stderr);
      
      res.setHeader('Content-Type', 'application/json');
      res.end(JSON.stringify({ status: 'started' }));
    });
  }
});

// https://vite.dev/config/
export default defineConfig({
  base: '/integrity/',
  plugins: [react(), demoPlugin()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './tests/setup.ts',
    include: ['src/**/*.test.{ts,tsx}', 'tests/unit/**/*.test.{ts,tsx}'],
  },
})
