import path from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/projects': 'http://127.0.0.1:8000',
      '/health': 'http://127.0.0.1:8000',
      '/settings': 'http://127.0.0.1:8000',
      // The Ignition Tag Builder backend mounts under /api/ignition-tags.
      '/api': 'http://127.0.0.1:8000',
      // Note: /projects already covers /projects/{id}/export; listed for clarity.
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
});
