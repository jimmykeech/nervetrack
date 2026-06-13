import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// The backend base URL. In Docker compose this is the service name; locally
// it defaults to localhost:8000.
const API_TARGET = process.env.VITE_API_PROXY ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [sveltekit()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true
      }
    }
  },
  test: {
    environment: 'node',
    include: ['src/**/*.{test,spec}.{js,ts}']
  }
});
