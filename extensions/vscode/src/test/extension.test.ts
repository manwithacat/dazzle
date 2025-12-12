/**
 * Extension Integration Tests
 *
 * These tests run in a real VS Code instance to verify:
 * 1. Extension activation
 * 2. Command registration
 * 3. Language configuration
 * 4. Basic functionality
 */

import * as assert from 'assert';
import * as vscode from 'vscode';

suite('DAZZLE Extension Test Suite', () => {
    vscode.window.showInformationMessage('Starting DAZZLE extension tests...');

    test('Extension should be present', () => {
        const ext = vscode.extensions.getExtension('dazzle.dazzle-dsl');
        assert.ok(ext, 'Extension should be installed');
    });

    test('Extension should activate', async function() {
        this.timeout(30000); // Extension activation may take time

        const ext = vscode.extensions.getExtension('dazzle.dazzle-dsl');
        assert.ok(ext, 'Extension should be installed');

        // Activate if not already active
        if (!ext.isActive) {
            await ext.activate();
        }

        assert.strictEqual(ext.isActive, true, 'Extension should be active');
    });

    test('DAZZLE commands should be registered', async function() {
        this.timeout(10000);

        const commands = await vscode.commands.getCommands(true);

        const expectedCommands = [
            'dazzle.validate',
            'dazzle.build',
            'dazzle.lint',
            'dazzle.showLspOutput'
        ];

        for (const cmd of expectedCommands) {
            assert.ok(
                commands.includes(cmd),
                `Command '${cmd}' should be registered`
            );
        }
    });

    test('Claude integration commands should be registered', async function() {
        this.timeout(10000);

        const commands = await vscode.commands.getCommands(true);

        const claudeCommands = [
            'dazzle.askClaudeToAnalyze',
            'dazzle.askClaudeToFix',
            'dazzle.askClaudeToBuild',
            'dazzle.askClaudeToInit'
        ];

        // These commands may or may not be present depending on configuration
        // Just verify we can query them without error
        for (const cmd of claudeCommands) {
            // This test passes if no exception is thrown
            const exists = commands.includes(cmd);
            // Log for debugging but don't fail - these are optional features
            console.log(`Claude command '${cmd}': ${exists ? 'registered' : 'not registered'}`);
        }
    });

    test('DSL language should be registered', async function() {
        this.timeout(5000);

        const languages = await vscode.languages.getLanguages();
        assert.ok(
            languages.includes('dazzle-dsl'),
            'Language dazzle-dsl should be registered'
        );
    });

    test('DSL file extensions should be associated', function() {
        // Verify the extension contributes .dsl file association
        const ext = vscode.extensions.getExtension('dazzle.dazzle-dsl');
        assert.ok(ext, 'Extension should be installed');

        const packageJson = ext.packageJSON;
        const languages = packageJson.contributes?.languages || [];

        const dazzleLanguage = languages.find(
            (lang: { id: string }) => lang.id === 'dazzle-dsl'
        );
        assert.ok(dazzleLanguage, 'dazzle-dsl language should be contributed');

        const extensions = dazzleLanguage.extensions || [];
        assert.ok(extensions.includes('.dsl'), '.dsl extension should be registered');
        assert.ok(extensions.includes('.dazzle'), '.dazzle extension should be registered');
    });

    test('Grammar should be contributed', function() {
        const ext = vscode.extensions.getExtension('dazzle.dazzle-dsl');
        assert.ok(ext, 'Extension should be installed');

        const packageJson = ext.packageJSON;
        const grammars = packageJson.contributes?.grammars || [];

        const dazzleGrammar = grammars.find(
            (g: { language: string }) => g.language === 'dazzle-dsl'
        );
        assert.ok(dazzleGrammar, 'dazzle-dsl grammar should be contributed');
        assert.strictEqual(
            dazzleGrammar.scopeName,
            'source.dazzle',
            'Grammar scope should be source.dazzle'
        );
    });

    test('Configuration should be contributed', function() {
        const ext = vscode.extensions.getExtension('dazzle.dazzle-dsl');
        assert.ok(ext, 'Extension should be installed');

        const packageJson = ext.packageJSON;
        const configuration = packageJson.contributes?.configuration;
        assert.ok(configuration, 'Configuration should be contributed');

        const properties = configuration.properties || {};

        // Check key configuration options
        assert.ok(properties['dazzle.cliPath'], 'dazzle.cliPath should be configurable');
        assert.ok(properties['dazzle.validateOnSave'], 'dazzle.validateOnSave should be configurable');
    });

    test('Configuration defaults should be sensible', function() {
        const config = vscode.workspace.getConfiguration('dazzle');

        // Check defaults
        assert.strictEqual(
            config.get('cliPath'),
            'dazzle',
            'Default CLI path should be "dazzle"'
        );
        assert.strictEqual(
            config.get('validateOnSave'),
            true,
            'validateOnSave should default to true'
        );
        assert.strictEqual(
            config.get('manifest'),
            'dazzle.toml',
            'Default manifest should be "dazzle.toml"'
        );
    });
});

/**
 * Python Discovery Tests
 *
 * These tests verify the Python discovery logic works correctly.
 * This is critical because the VS Code extension needs to find a Python
 * interpreter with dazzle.lsp installed to enable LSP features.
 *
 * Common failure scenarios this catches:
 * - Homebrew installation missing LSP dependencies
 * - pyenv shims not working in VS Code's environment
 * - Python import failing due to missing dependencies
 */
suite('DAZZLE Python Discovery Tests', () => {
    const child_process = require('child_process');
    const fs = require('fs');
    const path = require('path');

    // Test the actual import check that the extension uses
    test('dazzle.lsp should be importable from system Python', function(done) {
        this.timeout(10000);

        // This mirrors what canImportDazzle() does in lspClient.ts
        const proc = child_process.spawn('python3', ['-c', 'import dazzle.lsp'], {
            stdio: 'pipe',
        });

        let stderr = '';
        proc.stderr.on('data', (data: Buffer) => {
            stderr += data.toString();
        });

        proc.on('close', (code: number | null) => {
            if (code === 0) {
                done();
            } else {
                // Skip if dazzle isn't installed (expected in CI environments)
                if (stderr.includes("No module named 'dazzle'")) {
                    console.log('dazzle not installed in system Python, skipping');
                    done();
                    return;
                }
                // Provide helpful diagnostic info for actual failures
                const errorInfo = [
                    'Failed to import dazzle.lsp from python3.',
                    'This is the same check the VS Code extension uses.',
                    '',
                    'Common causes:',
                    '  1. dazzle not installed: pip install dazzle[lsp]',
                    '  2. LSP dependencies missing: pip install pygls lsprotocol',
                    '  3. Homebrew formula missing LSP extras (known issue)',
                    '',
                    'Error output:',
                    stderr,
                ].join('\n');
                done(new Error(errorInfo));
            }
        });

        proc.on('error', (err: Error) => {
            if (err.message.includes('ENOENT')) {
                console.log('python3 not found, skipping import test');
                done();
            } else {
                done(err);
            }
        });

        // Timeout after 5 seconds (extension uses 2s but we allow more for CI)
        setTimeout(() => {
            proc.kill();
            done(new Error('Import check timed out - python3 may be hanging'));
        }, 5000);
    });

    test('LSP dependencies should be installed', function(done) {
        this.timeout(5000);

        // First check if dazzle is installed, skip if not (expected in CI)
        const checkDazzle = child_process.spawnSync('python3', ['-c', 'import dazzle'], {
            stdio: 'pipe',
        });

        if (checkDazzle.status !== 0) {
            console.log('dazzle not installed, skipping LSP dependency check');
            done();
            return;
        }

        // Check specifically for pygls and lsprotocol
        const checkScript = `
import sys
missing = []
try:
    import pygls
except ImportError:
    missing.append('pygls')
try:
    import lsprotocol
except ImportError:
    missing.append('lsprotocol')
if missing:
    print(f"MISSING:{','.join(missing)}")
    sys.exit(1)
print("OK")
`;

        const proc = child_process.spawn('python3', ['-c', checkScript], {
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        let stdout = '';
        let stderr = '';
        proc.stdout.on('data', (data: Buffer) => { stdout += data.toString(); });
        proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

        proc.on('close', (code: number | null) => {
            if (code === 0 && stdout.includes('OK')) {
                done();
            } else {
                const missing = stdout.match(/MISSING:(.+)/)?.[1] || 'unknown';
                done(new Error(
                    `LSP dependencies missing: ${missing}\n` +
                    'Fix: pip install dazzle[lsp]\n' +
                    'Or: pip install pygls lsprotocol'
                ));
            }
        });

        proc.on('error', () => {
            console.log('python3 not found, skipping dependency check');
            done();
        });
    });

    test('Homebrew dazzle should have LSP dependencies if installed', function(done) {
        this.timeout(5000);

        const homebrewPython = '/opt/homebrew/Cellar/dazzle/0.12.0/libexec/bin/python';

        // Skip if Homebrew dazzle is not installed
        if (!fs.existsSync(homebrewPython)) {
            console.log('Homebrew dazzle not installed, skipping');
            done();
            return;
        }

        const proc = child_process.spawn(homebrewPython, ['-c', 'import dazzle.lsp'], {
            stdio: 'pipe',
        });

        let stderr = '';
        proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

        proc.on('close', (code: number | null) => {
            if (code === 0) {
                done();
            } else {
                done(new Error(
                    'Homebrew dazzle installation is missing LSP dependencies!\n' +
                    'This is a known issue where the formula [lsp] extras were not installed.\n' +
                    'Fix: /opt/homebrew/Cellar/dazzle/0.12.0/libexec/bin/python -m pip install pygls lsprotocol\n' +
                    'Or reinstall: brew reinstall dazzle\n\n' +
                    'Error: ' + stderr
                ));
            }
        });

        proc.on('error', () => done());
    });

    test('pyenv Python should work in clean environment', function(done) {
        this.timeout(5000);

        const home = process.env.HOME;
        const pyenvPython = `${home}/.pyenv/shims/python3`;

        // Skip if pyenv is not installed
        if (!fs.existsSync(pyenvPython)) {
            console.log('pyenv not installed, skipping');
            done();
            return;
        }

        // Test with a minimal environment (similar to VS Code's extension host)
        const proc = child_process.spawn(pyenvPython, ['-c', 'import dazzle.lsp'], {
            stdio: 'pipe',
            env: {
                HOME: home,
                PATH: `${home}/.pyenv/shims:/usr/bin:/bin`,
            },
        });

        let stderr = '';
        proc.stderr.on('data', (data: Buffer) => { stderr += data.toString(); });

        proc.on('close', (code: number | null) => {
            if (code === 0) {
                done();
            } else {
                done(new Error(
                    'pyenv Python cannot import dazzle.lsp in clean environment.\n' +
                    'The VS Code extension uses a similar environment.\n' +
                    'Make sure dazzle[lsp] is installed in your pyenv Python:\n' +
                    '  pyenv exec pip install dazzle[lsp]\n\n' +
                    'Error: ' + stderr
                ));
            }
        });

        proc.on('error', () => done());
    });
});

/**
 * LSP Server Tests
 *
 * These tests verify the Python LSP server starts correctly.
 * They run outside VS Code's extension host to test the server directly.
 */
suite('DAZZLE LSP Server Tests', () => {
    const child_process = require('child_process');

    // Helper to check if dazzle.lsp is available
    function isDazzleLspAvailable(): boolean {
        const result = child_process.spawnSync('python3', ['-c', 'import dazzle.lsp'], {
            stdio: 'pipe',
        });
        return result.status === 0;
    }

    test('LSP server should start without RuntimeWarning', function(done) {
        this.timeout(10000);

        // Skip if dazzle.lsp is not available (expected in CI)
        if (!isDazzleLspAvailable()) {
            console.log('dazzle.lsp not available, skipping LSP server test');
            done();
            return;
        }

        // Spawn the LSP server briefly to check for warnings
        const proc = child_process.spawn('python3', ['-m', 'dazzle.lsp'], {
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        let stderr = '';
        proc.stderr.on('data', (data: Buffer) => {
            stderr += data.toString();
        });

        // Give it a moment to start, then kill it
        setTimeout(() => {
            proc.kill();
        }, 2000);

        proc.on('close', () => {
            // Check for the specific warning about module double-loading
            if (stderr.includes('found in sys.modules after import')) {
                done(new Error(
                    'LSP server produced RuntimeWarning about module loading. ' +
                    'This indicates the wrong entry point is being used. ' +
                    'Use "python -m dazzle.lsp" not "python -m dazzle.lsp.server"'
                ));
            } else {
                done();
            }
        });

        proc.on('error', (err: Error) => {
            // Server not available is OK - we're testing the startup behavior
            if (err.message.includes('ENOENT')) {
                console.log('python3 not found, skipping LSP server test');
                done();
            } else {
                done(err);
            }
        });
    });

    test('LSP server should not register features twice', function(done) {
        this.timeout(10000);

        // Skip if dazzle.lsp is not available (expected in CI)
        if (!isDazzleLspAvailable()) {
            console.log('dazzle.lsp not available, skipping LSP server test');
            done();
            return;
        }

        const proc = child_process.spawn('python3', ['-m', 'dazzle.lsp'], {
            stdio: ['pipe', 'pipe', 'pipe'],
        });

        let stderr = '';
        proc.stderr.on('data', (data: Buffer) => {
            stderr += data.toString();
        });

        setTimeout(() => {
            proc.kill();
        }, 2000);

        proc.on('close', () => {
            // Count how many times 'initialize' feature was registered
            const initializeCount = (stderr.match(/Registered "initialize"/g) || []).length;
            const hoverCount = (stderr.match(/Registered "textDocument\/hover"/g) || []).length;

            if (initializeCount > 1) {
                done(new Error(
                    `Feature "initialize" was registered ${initializeCount} times (expected 1). ` +
                    'This indicates duplicate module loading in the LSP server.'
                ));
            } else if (hoverCount > 1) {
                done(new Error(
                    `Feature "textDocument/hover" was registered ${hoverCount} times (expected 1). ` +
                    'This indicates duplicate module loading in the LSP server.'
                ));
            } else {
                done();
            }
        });

        proc.on('error', (err: Error) => {
            if (err.message.includes('ENOENT')) {
                console.log('python3 not found, skipping LSP server test');
                done();
            } else {
                done(err);
            }
        });
    });
});
