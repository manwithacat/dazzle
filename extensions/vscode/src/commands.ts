import * as vscode from 'vscode';
import * as child_process from 'child_process';
import { DazzleDiagnostics } from './diagnostics';

/**
 * DAZZLE CLI Commands
 *
 * Implements VS Code commands that invoke DAZZLE CLI
 */

export function registerCommands(
    context: vscode.ExtensionContext,
    diagnostics: DazzleDiagnostics
): void {
    // Register validate command
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

    // Register lint command
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
        terminal.sendText(`${cliPath} lint`);
    });

    context.subscriptions.push(validateCmd, buildCmd, lintCmd);
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
