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

let outputChannel: vscode.OutputChannel | undefined;

/**
 * Get or create the LSP output channel.
 */
function getOutputChannel(): vscode.OutputChannel {
    if (!outputChannel) {
        outputChannel = vscode.window.createOutputChannel('Dazzle Language Server');
        // Make sure the channel is visible in the output panel
        outputChannel.show(true);
    }
    return outputChannel;
}

/**
 * Start the LSP client and connect to the Python LSP server.
 */
export async function startLanguageClient(context: vscode.ExtensionContext): Promise<void> {
    const config = vscode.workspace.getConfiguration('dazzle');
    const pythonPath = getPythonPath();
    const channel = getOutputChannel();

    channel.appendLine('='.repeat(60));
    channel.appendLine('Dazzle Language Server Starting...');
    channel.appendLine('This channel shows LSP messages (hover, completions, diagnostics)');
    channel.appendLine(`Python path: ${pythonPath}`);
    channel.appendLine(`Timestamp: ${new Date().toISOString()}`);
    channel.appendLine('='.repeat(60));

    // Check if LSP server is available before starting
    channel.appendLine('Checking if DAZZLE LSP server is available...');
    const isAvailable = await checkLspServerAvailable();

    if (!isAvailable) {
        channel.appendLine('❌ DAZZLE LSP server not found');
        channel.appendLine(`Tried to import: python3 -c "import dazzle.lsp.server"`);
        channel.appendLine('');
        channel.appendLine('To enable LSP features:');
        channel.appendLine('  1. Install dazzle: pip install dazzle');
        channel.appendLine('  2. Or for development: pip install -e /path/to/dazzle');
        channel.appendLine('  3. Verify: python3 -c "import dazzle.lsp.server"');
        channel.show();

        const action = await vscode.window.showWarningMessage(
            `DAZZLE LSP server not found. Check the DAZZLE LSP output panel for details.`,
            'Show Output',
            'Show Setup Guide'
        );

        if (action === 'Show Output') {
            channel.show();
        } else if (action === 'Show Setup Guide') {
            vscode.env.openExternal(vscode.Uri.parse('https://github.com/dazzle/dazzle#installation'));
        }

        // Don't start LSP, but don't throw error - extension can still work for basic features
        return;
    }

    channel.appendLine('✅ DAZZLE LSP server is available');
    channel.appendLine('');

    // Server options: spawn the Python LSP server
    const serverOptions: ServerOptions = {
        command: pythonPath,
        args: ['-m', 'dazzle.lsp.server'],
        transport: TransportKind.stdio,
        options: {
            env: {
                ...process.env,
                // Inherit existing PYTHONPATH without modification
                // Development installations should set PYTHONPATH themselves
            }
        }
    };

    channel.appendLine(`Starting LSP server: ${pythonPath} -m dazzle.lsp.server`);

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
        outputChannel: channel,
    };

    // Create and start the client
    client = new LanguageClient(
        'dazzle-lsp',
        'DAZZLE Language Server',
        serverOptions,
        clientOptions
    );

    try {
        channel.appendLine('Starting language client...');
        await client.start();
        channel.appendLine('✅ DAZZLE Language Server started successfully');
        channel.appendLine('');
        channel.appendLine('LSP features enabled:');
        channel.appendLine('  • Hover information (Ctrl/Cmd + hover)');
        channel.appendLine('  • Go to definition (Ctrl/Cmd + click)');
        channel.appendLine('  • Auto-completion');
        channel.appendLine('  • Document symbols');
        console.log('DAZZLE Language Server started successfully');
    } catch (error) {
        channel.appendLine(`❌ Failed to start DAZZLE Language Server: ${error}`);
        channel.appendLine('');
        channel.appendLine('Troubleshooting:');
        channel.appendLine('  1. Check that dazzle is installed: pip list | grep dazzle');
        channel.appendLine('  2. Try running manually: python3 -m dazzle.lsp');
        channel.appendLine('  3. Check Python path in settings: dazzle.pythonPath');
        channel.show();

        vscode.window.showErrorMessage(
            `Failed to start DAZZLE Language Server. Check the DAZZLE LSP output panel for details.`,
            'Show Output'
        ).then(action => {
            if (action === 'Show Output') {
                channel.show();
            }
        });
        // Don't throw - allow extension to work without LSP
    }

    context.subscriptions.push({
        dispose: () => {
            if (client) {
                client.stop();
            }
            if (outputChannel) {
                outputChannel.dispose();
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
