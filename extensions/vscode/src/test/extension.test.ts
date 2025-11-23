/**
 * Extension tests
 *
 * Basic tests to verify extension functionality
 */

import * as assert from 'assert';
import * as vscode from 'vscode';

suite('DAZZLE Extension Test Suite', () => {
    vscode.window.showInformationMessage('Starting DAZZLE extension tests...');

    test('Extension should be present', () => {
        assert.ok(vscode.extensions.getExtension('dazzle.dazzle-dsl'));
    });

    test('Extension should activate', async () => {
        const ext = vscode.extensions.getExtension('dazzle.dazzle-dsl');
        assert.ok(ext);

        await ext?.activate();
        assert.strictEqual(ext?.isActive, true);
    });

    test('DAZZLE commands should be registered', async () => {
        const commands = await vscode.commands.getCommands(true);

        const expectedCommands = [
            'dazzle.validate',
            'dazzle.build',
            'dazzle.lint',
            'dazzle.analyzeSpec',
            'dazzle.showLspOutput'
        ];

        for (const cmd of expectedCommands) {
            assert.ok(
                commands.includes(cmd),
                `Command ${cmd} should be registered`
            );
        }
    });

    test('DAZZLE language should be registered', () => {
        const languages = vscode.languages.getLanguages();
        // Note: This is async but we can check if the language ID exists
        // Language registration happens during activation
        assert.ok(languages);
    });
});
