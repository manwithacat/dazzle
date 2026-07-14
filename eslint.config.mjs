// Structural ESLint only -- no style opinions.
// Globs (ADR-0053 / #1585 — HM owns design-system UI; page is product glue):
//   packages/hatchi-maxchi/controllers  -- HM Hyperpart controllers (decision 0010)
//   src/dazzle/page/**/js               -- product page runtime JS (ADR-0041 rename)
// Path src/dazzle_ui/** does not exist — never re-add it.

const browserGlobals = {
  window: "readonly",
  document: "readonly",
  console: "readonly",
  setTimeout: "readonly",
  setInterval: "readonly",
  clearTimeout: "readonly",
  clearInterval: "readonly",
  fetch: "readonly",
  requestAnimationFrame: "readonly",
  cancelAnimationFrame: "readonly",
  MutationObserver: "readonly",
  IntersectionObserver: "readonly",
  ResizeObserver: "readonly",
  matchMedia: "readonly",
  getComputedStyle: "readonly",
  CSS: "readonly",
  FormData: "readonly",
  URL: "readonly",
  URLSearchParams: "readonly",
  CustomEvent: "readonly",
  Event: "readonly",
  KeyboardEvent: "readonly",
  MouseEvent: "readonly",
  PointerEvent: "readonly",
  FocusEvent: "readonly",
  HTMLElement: "readonly",
  HTMLDialogElement: "readonly",
  HTMLInputElement: "readonly",
  HTMLCanvasElement: "readonly",
  CanvasRenderingContext2D: "readonly",
  Node: "readonly",
  NodeList: "readonly",
  Element: "readonly",
  localStorage: "readonly",
  sessionStorage: "readonly",
  navigator: "readonly",
  location: "readonly",
  history: "readonly",
  crypto: "readonly",
  confirm: "readonly",
  alert: "readonly",
  prompt: "readonly",
  NodeFilter: "readonly",
  DOMParser: "readonly",
  AbortController: "readonly",
  queueMicrotask: "readonly",
  structuredClone: "readonly",
  // Frameworks / libs loaded via script tags or dynamic import
  Alpine: "readonly",
  htmx: "readonly",
  lucide: "readonly",
  Sortable: "readonly",
  Quill: "readonly",
  flatpickr: "readonly",
  TomSelect: "readonly",
  Pickr: "readonly",
  pdfjsLib: "readonly",
};

const structuralRules = {
  "no-undef": "error",
  "no-unreachable": "error",
  "no-dupe-keys": "error",
  "no-duplicate-case": "error",
  "no-empty-pattern": "error",
  "no-func-assign": "error",
  "no-import-assign": "error",
  "no-invalid-regexp": "error",
  "no-irregular-whitespace": "error",
  "no-loss-of-precision": "error",
  "no-unexpected-multiline": "error",
  "constructor-super": "error",
  "valid-typeof": "error",
};

export default [
  {
    files: [
      "packages/hatchi-maxchi/controllers/**/*.js",
      "src/dazzle/page/**/js/**/*.js",
    ],
    ignores: ["**/vendor/**", "**/dist/**", "**/*.min.js", "**/islands/**"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "script",
      globals: browserGlobals,
    },
    rules: structuralRules,
  },
  // ES-module islands (signing-pad, etc.)
  {
    files: ["src/dazzle/page/**/js/islands/**/*.js"],
    ignores: ["**/vendor/**", "**/dist/**", "**/*.min.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: browserGlobals,
    },
    rules: structuralRules,
  },
];
