import { defineConfig } from "vitest/config";

// ADR-0041: package is dazzle.page (was dazzle_ui). Product page JS lives under
// src/dazzle/page/runtime/static/js/. HM Hyperpart controllers are gated by
// dual-lock + Playwright, not vitest — see ADR-0053 / decision 0010.
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["src/dazzle/page/runtime/static/js/**/*.test.js"],
    globals: true,
  },
});
