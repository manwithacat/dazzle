import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/dazzle_dnr_ui/runtime/static/js/**/*.test.js'],
    globals: true,
  },
});
