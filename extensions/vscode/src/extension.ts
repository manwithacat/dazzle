import * as vscode from 'vscode';
import { DazzleDiagnostics } from './diagnostics';
import { registerCommands } from './commands';
import { registerLLMCommands } from './llmCommands';
import { startLanguageClient, stopLanguageClient, checkLspServerAvailable } from './lspClient';

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

export async function activate(context: vscode.ExtensionContext) {
    console.log('DAZZLE DSL extension is now active');

    // Initialize diagnostics provider
    diagnostics = new DazzleDiagnostics();
    context.subscriptions.push(diagnostics);

    // Register commands (validate, build, lint)
    registerCommands(context, diagnostics);

    // Register LLM commands (analyze-spec, etc.)
    registerLLMCommands(context);

    // Set up file watchers for auto-validation
    setupFileWatchers(context);

    // Start LSP client if available
    const lspAvailable = await checkLspServerAvailable();
    if (lspAvailable) {
        try {
            await startLanguageClient(context);
            lspClientActive = true;
            console.log('DAZZLE LSP client started successfully');
        } catch (error) {
            console.error('Failed to start LSP client:', error);
            vscode.window.showWarningMessage(
                'DAZZLE LSP features unavailable. Install DAZZLE with: pip install dazzle',
                'Learn More'
            ).then(selection => {
                if (selection === 'Learn More') {
                    vscode.env.openExternal(vscode.Uri.parse('https://github.com/dazzle/dazzle'));
                }
            });
        }
    } else {
        console.log('DAZZLE LSP server not found, LSP features will be unavailable');
    }

    // Show welcome message on first activation
    const hasShownWelcome = context.globalState.get('dazzle.hasShownWelcome', false);
    if (!hasShownWelcome) {
        const lspStatus = lspClientActive ? 'LSP features enabled' : 'LSP features unavailable';
        vscode.window.showInformationMessage(
            `DAZZLE DSL extension activated! Syntax highlighting and validation are now available. ${lspStatus}.`,
            'Learn More'
        ).then(selection => {
            if (selection === 'Learn More') {
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
    if (lspClientActive) {
        await stopLanguageClient();
    }
}
