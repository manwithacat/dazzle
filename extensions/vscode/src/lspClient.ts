/**
 * DAZZLE Language Server Protocol Client
 *
 * Manages the connection to the Python-based DAZZLE LSP server.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from 'vscode-languageclient/node';

let client: LanguageClient | undefined;

/**
 * Start the LSP client and connect to the Python LSP server.
 */
export async function startLanguageClient(context: vscode.ExtensionContext): Promise<void> {
    const config = vscode.workspace.getConfiguration('dazzle');
    const pythonPath = getPythonPath();

    // Check if LSP server is available before starting
    const isAvailable = await checkLspServerAvailable();
    if (!isAvailable) {
        const action = await vscode.window.showWarningMessage(
            `DAZZLE LSP server not found. The Python package 'dazzle' is not installed in ${pythonPath}.\n\n` +
            `To enable language features:\n` +
            `1. Install dazzle: pip install -e /Volumes/SSD/Dazzle\n` +
            `2. Or set DAZZLE_PYTHON environment variable to correct Python path\n` +
            `3. Or install dazzle in current Python: ${pythonPath}`,
            'Show Setup Guide',
            'Disable LSP'
        );

        if (action === 'Show Setup Guide') {
            vscode.env.openExternal(vscode.Uri.parse('https://github.com/dazzle/dazzle#development-setup'));
        }

        // Don't start LSP, but don't throw error - extension can still work for basic features
        return;
    }

    // Server options: spawn the Python LSP server
    const serverOptions: ServerOptions = {
        command: pythonPath,
        args: ['-m', 'dazzle.lsp'],
        transport: TransportKind.stdio,
        options: {
            env: {
                ...process.env,
                // Support development mode: add project root to PYTHONPATH
                PYTHONPATH: `/Volumes/SSD/Dazzle/src${process.env.PYTHONPATH ? ':' + process.env.PYTHONPATH : ''}`
            }
        }
    };

    // Client options: configure which files to watch
    const clientOptions: LanguageClientOptions = {
        // Register the server for DAZZLE DSL files
        documentSelector: [
            { scheme: 'file', language: 'dazzle-dsl' },
            { scheme: 'file', pattern: '**/*.dsl' },
        ],
        synchronize: {
            // Notify the server about file changes to .dsl and .toml files
            fileEvents: vscode.workspace.createFileSystemWatcher('**/*.{dsl,toml}'),
        },
        outputChannel: vscode.window.createOutputChannel('DAZZLE LSP'),
    };

    // Create and start the client
    client = new LanguageClient(
        'dazzle-lsp',
        'DAZZLE Language Server',
        serverOptions,
        clientOptions
    );

    try {
        await client.start();
        console.log('DAZZLE Language Server started successfully');
    } catch (error) {
        vscode.window.showErrorMessage(`Failed to start DAZZLE Language Server: ${error}`);
        // Don't throw - allow extension to work without LSP
    }

    context.subscriptions.push({
        dispose: () => {
            if (client) {
                client.stop();
            }
        }
    });
}

/**
 * Stop the LSP client.
 */
export async function stopLanguageClient(): Promise<void> {
    if (client) {
        await client.stop();
        client = undefined;
    }
}

/**
 * Get the Python interpreter path.
 *
 * Checks for (in order):
 * 1. dazzle.pythonPath VS Code setting
 * 2. DAZZLE_PYTHON environment variable
 * 3. Python extension's active interpreter
 * 4. Falls back to 'python3'
 */
function getPythonPath(): string {
    // Check VS Code configuration first
    const config = vscode.workspace.getConfiguration('dazzle');
    const configuredPath = config.get<string>('pythonPath');
    if (configuredPath && configuredPath.trim() !== '') {
        return configuredPath;
    }

    // Check environment variable
    if (process.env.DAZZLE_PYTHON) {
        return process.env.DAZZLE_PYTHON;
    }

    // Try to get Python path from Python extension
    const pythonExtension = vscode.extensions.getExtension('ms-python.python');
    if (pythonExtension && pythonExtension.isActive) {
        const pythonPath = pythonExtension.exports?.settings?.getExecutionDetails?.()?.execCommand?.[0];
        if (pythonPath) {
            return pythonPath;
        }
    }

    // Default to python3
    return 'python3';
}

/**
 * Check if the DAZZLE LSP server is available.
 */
export async function checkLspServerAvailable(): Promise<boolean> {
    const pythonPath = getPythonPath();

    return new Promise((resolve) => {
        const child_process = require('child_process');
        // Use -c to check if module can be imported
        const proc = child_process.spawn(pythonPath, ['-c', 'import dazzle.lsp.server'], {
            stdio: 'pipe',
        });

        let stderr = '';
        proc.stderr?.on('data', (data: Buffer) => {
            stderr += data.toString();
        });

        proc.on('close', (code: number | null) => {
            // If code is 0, module imports successfully
            // If code is 1, check for ModuleNotFoundError
            const available = code === 0;
            if (!available) {
                console.log('DAZZLE LSP not available:', stderr.substring(0, 200));
            }
            resolve(available);
        });

        proc.on('error', (err: Error) => {
            console.error('Error checking LSP availability:', err);
            resolve(false);
        });

        // Timeout after 2 seconds
        setTimeout(() => {
            proc.kill();
            resolve(false);
        }, 2000);
    });
}
