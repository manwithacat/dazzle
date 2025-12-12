import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
    // Only run extension.test.js - other tests use BDD syntax and run via npm run test:python
    files: 'out/test/extension.test.js',
    version: 'stable',
    mocha: {
        ui: 'tdd',
        color: true,
        timeout: 60000
    }
});
