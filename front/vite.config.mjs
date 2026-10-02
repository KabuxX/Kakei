import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { mockApi } from './dev/mock-api.mjs';

export default defineConfig(({ mode }) => {
  const apiTarget = process.env.KAKEI_API_TARGET || 'http://127.0.0.1:8765';
  return {
    envDir: '..',
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
    build: { outDir: 'dist', assetsDir: 'assets' },
    test: { environment: 'jsdom', include: ['src/**/*.test.{js,jsx}'] },
  };
});
