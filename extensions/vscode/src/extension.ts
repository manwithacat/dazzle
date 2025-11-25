import * as vscode from 'vscode';
import { DazzleDiagnostics } from './diagnostics';
import { registerCommands } from './commands';
import { startLanguageClient, stopLanguageClient, checkLspServerAvailable } from './lspClient';
import {
    registerClaudeCommands,
    createSpecStatusBar,
    autoDetectSpec
} from './claudeIntegration';

/**
 * DAZZLE VS Code Extension
 *
 * This extension provides language support for DAZZLE DSL files.
 * Phase 1: Basic syntax highlighting ✓
 * Phase 2: CLI integration and diagnostics ✓
 * Phase 3: LSP features ✓
 */

let diagnostics: DazzleDiagnostics;
let fileWatcher: vscode.FileSystemWatcher | undefined;
let lspClientActive = false;
let specStatusBarItem: vscode.StatusBarItem | null = null;
let lspStatusBarItem: vscode.StatusBarItem | undefined;

export async function activate(context: vscode.ExtensionContext) {
    console.log('Dazzle DSL extension is now active');

    // Create LSP status bar item (show loading initially)
    lspStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    lspStatusBarItem.text = '$(loading~spin) Dazzle LSP';
    lspStatusBarItem.tooltip = 'Dazzle Language Server initializing...';
    lspStatusBarItem.command = 'dazzle.showLspOutput';
    lspStatusBarItem.show();
    context.subscriptions.push(lspStatusBarItem);

    // Register command to show LSP output
    context.subscriptions.push(
        vscode.commands.registerCommand('dazzle.showLspOutput', () => {
            const outputPanel = vscode.window.visibleTextEditors.find(editor =>
                editor.document.uri.scheme === 'output'
            );
            vscode.commands.executeCommand('workbench.action.output.show');
            // Select Dazzle Language Server in the output dropdown
            vscode.commands.executeCommand('workbench.action.output.toggleOutput', 'Dazzle Language Server');
        })
    );

    // Initialize diagnostics provider
    diagnostics = new DazzleDiagnostics();
    context.subscriptions.push(diagnostics);

    // Register commands (validate, build, lint)
    registerCommands(context, diagnostics);

    // Register Claude integration commands (simplified)
    registerClaudeCommands(context);

    // Set up status bar for SPEC → App workflow
    specStatusBarItem = createSpecStatusBar(context);

    // Auto-detect SPEC.md and show helpful notification
    setTimeout(() => autoDetectSpec(context), 3000);

    // Set up file watchers for auto-validation
    setupFileWatchers(context);

    // Start LSP client if available
    console.log('Checking for DAZZLE LSP server...');
    const lspAvailable = await checkLspServerAvailable();
    if (lspAvailable) {
        try {
            console.log('LSP server available, starting client...');
            await startLanguageClient(context);
            lspClientActive = true;
            lspStatusBarItem.text = '$(check) Dazzle LSP';
            lspStatusBarItem.tooltip = 'Dazzle Language Server: Active\nClick to show output';
            lspStatusBarItem.backgroundColor = undefined;
            console.log('DAZZLE LSP client started successfully');
        } catch (error) {
            console.error('Failed to start LSP client:', error);
            lspStatusBarItem.text = '$(warning) DAZZLE LSP';
            lspStatusBarItem.tooltip = `DAZZLE Language Server: Error\n${error}\nClick for details`;
            lspStatusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.warningBackground');

            vscode.window.showWarningMessage(
                'DAZZLE LSP features unavailable. Check the DAZZLE LSP output for details.',
                'Show Output',
                'Learn More'
            ).then(selection => {
                if (selection === 'Show Output') {
                    vscode.commands.executeCommand('dazzle.showLspOutput');
                } else if (selection === 'Learn More') {
                    vscode.env.openExternal(vscode.Uri.parse('https://github.com/dazzle/dazzle'));
                }
            });
        }
    } else {
        console.log('DAZZLE LSP server not found, LSP features will be unavailable');
        lspStatusBarItem.text = '$(x) DAZZLE LSP';
        lspStatusBarItem.tooltip = 'DAZZLE Language Server: Not Available\nInstall: pip install dazzle\nClick for details';
        lspStatusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
    }

    // Show welcome message on first activation
    const hasShownWelcome = context.globalState.get('dazzle.hasShownWelcome', false);
    if (!hasShownWelcome) {
        const lspStatus = lspClientActive ? 'LSP features enabled ✓' : 'LSP features unavailable (install: pip install dazzle)';
        vscode.window.showInformationMessage(
            `DAZZLE DSL extension activated! ${lspStatus}`,
            'Show LSP Status',
            'Learn More'
        ).then(selection => {
            if (selection === 'Show LSP Status') {
                vscode.commands.executeCommand('dazzle.showLspOutput');
            } else if (selection === 'Learn More') {
                vscode.env.openExternal(vscode.Uri.parse('https://github.com/dazzle/dazzle'));
            }
        });
        context.globalState.update('dazzle.hasShownWelcome', true);
    }

    // Validate workspace on activation
    checkAndValidateWorkspace();
}

/**
 * Set up file watchers for DSL files and dazzle.toml
 */
function setupFileWatchers(context: vscode.ExtensionContext): void {
    const config = vscode.workspace.getConfiguration('dazzle');
    const validateOnSave = config.get<boolean>('validateOnSave', true);

    if (!validateOnSave) {
        return;
    }

    // Watch .dsl and dazzle.toml files
    fileWatcher = vscode.workspace.createFileSystemWatcher('**/*.{dsl,toml}');

    fileWatcher.onDidChange(async (uri) => {
        if (shouldValidateFile(uri)) {
            await validateCurrentWorkspace();
        }
    });

    fileWatcher.onDidCreate(async (uri) => {
        if (shouldValidateFile(uri)) {
            await validateCurrentWorkspace();
        }
    });

    fileWatcher.onDidDelete(async (uri) => {
        if (shouldValidateFile(uri)) {
            await validateCurrentWorkspace();
        }
    });

    context.subscriptions.push(fileWatcher);

    // Also validate on document save
    const saveWatcher = vscode.workspace.onDidSaveTextDocument(async (document) => {
        if (shouldValidateFile(document.uri)) {
            await validateCurrentWorkspace();
        }
    });

    context.subscriptions.push(saveWatcher);
}

/**
 * Check if file should trigger validation
 */
function shouldValidateFile(uri: vscode.Uri): boolean {
    const fileName = uri.fsPath;
    return fileName.endsWith('.dsl') || fileName.endsWith('dazzle.toml');
}

/**
 * Validate the current workspace
 */
async function validateCurrentWorkspace(): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        return;
    }

    // Validate first workspace folder with dazzle.toml
    for (const folder of workspaceFolders) {
        const manifestPath = vscode.Uri.joinPath(folder.uri, 'dazzle.toml');
        try {
            await vscode.workspace.fs.stat(manifestPath);
            // Found dazzle.toml, validate this workspace
            await diagnostics.validateWorkspace(folder);
            return;
        } catch {
            // No dazzle.toml in this folder, try next
        }
    }
}

/**
 * Check workspace and run initial validation
 */
function checkAndValidateWorkspace(): void {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders) {
        for (const folder of workspaceFolders) {
            const manifestPath = vscode.Uri.joinPath(folder.uri, 'dazzle.toml');
            vscode.workspace.fs.stat(manifestPath).then(
                () => {
                    console.log('DAZZLE project detected in workspace');
                    // Run initial validation
                    const config = vscode.workspace.getConfiguration('dazzle');
                    const validateOnSave = config.get<boolean>('validateOnSave', true);
                    if (validateOnSave) {
                        diagnostics.validateWorkspace(folder);
                    }
                },
                () => {
                    // No dazzle.toml found
                }
            );
        }
    }
}

export async function deactivate() {
    console.log('DAZZLE DSL extension deactivated');
    if (fileWatcher) {
        fileWatcher.dispose();
    }
    if (specStatusBarItem) {
        specStatusBarItem.dispose();
    }
    if (lspStatusBarItem) {
        lspStatusBarItem.dispose();
    }
    if (lspClientActive) {
        await stopLanguageClient();
    }
}
