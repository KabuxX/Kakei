import {fileURLToPath} from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { mockApi } from './dev/mock-api.mjs';

export default defineConfig(({ mode }) => {
  const apiTarget = process.env.KAKEI_API_TARGET || 'http://127.0.0.1:8765';
  return {
    envDir: mode === 'demo' ? 'demo' : '..',
    base: mode === 'demo' ? '/Kakei/' : '/',
    publicDir: mode === 'demo' ? 'demo/public' : 'public',
    resolve: {alias: {'@kakei/runtime': fileURLToPath(new URL(mode === 'demo' ? './demo/runtime.js' : './src/lib/runtime.js', import.meta.url))}},
    plugins: [react(), ...(mode === 'mock' ? [mockApi()] : [])],
    server: {
      proxy: mode === 'api' ? {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          configure(proxy) {
            proxy.on('proxyReq', (proxyRequest, request) => {
              if (request.headers.origin) proxyRequest.setHeader('Origin', new URL(apiTarget).origin);
            });
          },
        },
      } : undefined,
    },
    build: { outDir: mode === 'demo' ? 'dist-demo' : 'dist', assetsDir: 'assets' },
    test: { environment: 'jsdom', include: ['src/**/*.test.{js,jsx}'] },
  };
});
