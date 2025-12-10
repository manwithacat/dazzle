import * as vscode from 'vscode';
import * as child_process from 'child_process';
import { DazzleDiagnostics } from './diagnostics';

/**
 * DAZZLE CLI Commands (v0.8.0)
 *
 * Implements VS Code commands that invoke the new Bun-based DAZZLE CLI.
 *
 * CLI Command Changes in v0.8.0:
 * - validate -> check (with --json for machine output)
 * - lint -> check --strict
 * - build unchanged
 * - new: dev, show, test, db, eject commands
 */

export function registerCommands(
    context: vscode.ExtensionContext,
    diagnostics: DazzleDiagnostics
): void {
    // Register validate command (maps to 'check' in v0.8.0)
    const validateCmd = vscode.commands.registerCommand('dazzle.validate', async () => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            return;
        }

        await vscode.window.withProgress(
            {
                location: vscode.ProgressLocation.Notification,
                title: 'DAZZLE: Validating project...',
                cancellable: false
            },
            async () => {
                await diagnostics.validateWorkspace(workspaceFolder);
            }
        );
    });

    // Register build command
    const buildCmd = vscode.commands.registerCommand('dazzle.build', async () => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            return;
        }

        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        const terminal = vscode.window.createTerminal({
            name: 'DAZZLE Build',
            cwd: workspaceFolder.uri.fsPath
        });

        terminal.show();
        terminal.sendText(`${cliPath} build`);
    });

    // Register lint command (maps to 'check --strict' in v0.8.0)
    const lintCmd = vscode.commands.registerCommand('dazzle.lint', async () => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            return;
        }

        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        const terminal = vscode.window.createTerminal({
            name: 'DAZZLE Lint',
            cwd: workspaceFolder.uri.fsPath
        });

        terminal.show();
        // v0.8.0: lint is now 'check --strict'
        terminal.sendText(`${cliPath} check --strict`);
    });

    // Register dev command (new in v0.8.0)
    const devCmd = vscode.commands.registerCommand('dazzle.dev', async () => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            return;
        }

        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        const terminal = vscode.window.createTerminal({
            name: 'DAZZLE Dev Server',
            cwd: workspaceFolder.uri.fsPath
        });

        terminal.show();
        terminal.sendText(`${cliPath} dev`);
    });

    // Register test command (new in v0.8.0)
    const testCmd = vscode.commands.registerCommand('dazzle.test', async () => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            return;
        }

        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        const terminal = vscode.window.createTerminal({
            name: 'DAZZLE Test',
            cwd: workspaceFolder.uri.fsPath
        });

        terminal.show();
        terminal.sendText(`${cliPath} test`);
    });

    // Register eject command (new in v0.8.0)
    const ejectCmd = vscode.commands.registerCommand('dazzle.eject', async () => {
        const workspaceFolder = getWorkspaceFolder();
        if (!workspaceFolder) {
            return;
        }

        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        const terminal = vscode.window.createTerminal({
            name: 'DAZZLE Eject',
            cwd: workspaceFolder.uri.fsPath
        });

        terminal.show();
        terminal.sendText(`${cliPath} eject`);
    });

    context.subscriptions.push(validateCmd, buildCmd, lintCmd, devCmd, testCmd, ejectCmd);
}

/**
 * Get the current workspace folder
 */
function getWorkspaceFolder(): vscode.WorkspaceFolder | undefined {
    const workspaceFolders = vscode.workspace.workspaceFolders;

    if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showErrorMessage('No workspace folder open. Please open a DAZZLE project folder.');
        return undefined;
    }

    // If multiple workspace folders, try to find one with dazzle.toml
    if (workspaceFolders.length > 1) {
        for (const folder of workspaceFolders) {
            const manifestPath = vscode.Uri.joinPath(folder.uri, 'dazzle.toml');
            // We can't easily check if file exists here, so just use first folder
            // TODO: Implement proper workspace folder selection
        }
    }

    return workspaceFolders[0];
}
