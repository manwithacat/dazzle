import { defineConfig } from 'vite';

// API URL from environment variable or default to localhost
// In Docker, set VITE_API_URL=http://host.docker.internal:8000
const apiTarget = process.env.VITE_API_URL || 'http://localhost:8000';

export default defineConfig({
  root: 'src',
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    sourcemap: true,
  },
  server: {
    port: 3000,
    host: true,  // Listen on 0.0.0.0 for Docker access
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
      }
    }
  },
  resolve: {
    alias: {
      '@dnr': '/dnr'
    }
  }
});
