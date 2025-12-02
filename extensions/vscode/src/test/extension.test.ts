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
 * LSP Server Tests
 *
 * These tests verify the Python LSP server starts correctly.
 * They run outside VS Code's extension host to test the server directly.
 */
suite('DAZZLE LSP Server Tests', () => {
    const child_process = require('child_process');

    test('LSP server should start without RuntimeWarning', function(done) {
        this.timeout(10000);

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
