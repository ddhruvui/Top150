import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // API_PROXY lets a second local API (e.g. a sandbox on another port) sit
    // behind the dev server without editing this file.
    proxy: { '/api': { target: process.env.API_PROXY || 'http://localhost:8787', changeOrigin: true } },
  },
  build: { outDir: 'dist', sourcemap: false },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.js'],
    include: ['src/**/*.test.{js,jsx}'],
    css: false,
  },
});
