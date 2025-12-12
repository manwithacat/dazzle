import { defineConfig } from '@vscode/test-cli';

export default defineConfig({
    files: 'out/test/**/*.test.js',
    // Exclude python-discovery.test.js - it uses BDD syntax (describe/it) and runs via npx mocha
    // See: npm run test:python
    exclude: ['**/python-discovery.test.js'],
    version: 'stable',
    mocha: {
        ui: 'tdd',
        color: true,
        timeout: 60000
    }
});
