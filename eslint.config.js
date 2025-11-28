import globals from "globals";

export default [
  {
    files: ["src/dazzle_dnr_ui/runtime/static/js/**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
    rules: {
      // Error prevention
      "no-undef": "error",
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-redeclare": "error",
      "no-dupe-keys": "error",
      "no-duplicate-case": "error",
      "no-empty": "warn",
      "no-extra-semi": "error",
      "no-unreachable": "error",

      // Best practices
      "eqeqeq": ["warn", "always", { null: "ignore" }],
      "no-eval": "error",
      "no-implied-eval": "error",
      "no-new-func": "error",
      "no-var": "error",
      "prefer-const": "warn",

      // Style (minimal, non-blocking)
      "semi": ["warn", "always"],
      "quotes": ["warn", "single", { avoidEscape: true }],
    },
  },
];
