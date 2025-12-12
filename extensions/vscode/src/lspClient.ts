/**
 * DAZZLE Language Server Protocol Client
 *
 * Manages the connection to the Python-based DAZZLE LSP server.
 *
 * Architecture:
 * - Uses core/pythonDiscovery.ts for finding Python (no vscode dependency)
 * - Uses adapters/ for filesystem and process operations
 * - This file is the "thin adapter" that wires everything together with VS Code
 */

import * as vscode from 'vscode';
import {
    LanguageClient,
    LanguageClientOptions,
    ServerOptions,
    TransportKind,
} from 'vscode-languageclient/node';

// Core logic (no vscode imports)
import {
    findWorkingPython,
    formatDiscoveryResult,
    type Environment,
    type DiscoveryResult,
} from './core/pythonDiscovery';

// Adapters (production implementations)
import { nodeProcessRunner } from './adapters/nodeProcess';
import { nodeFileSystem } from './adapters/nodeFs';

let client: LanguageClient | undefined;
let outputChannel: vscode.OutputChannel | undefined;

// Cache discovery result for the session
let cachedDiscoveryResult: DiscoveryResult | null = null;

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
 * Build environment object from VS Code context.
 * This bridges VS Code APIs to our vscode-free core logic.
 */
function buildEnvironment(): Environment {
    const config = vscode.workspace.getConfiguration('dazzle');
    const workspaceFolders = vscode.workspace.workspaceFolders;

    // Try to get Python path from Python extension
    let pythonExtensionPath: string | undefined;
    const pythonExtension = vscode.extensions.getExtension('ms-python.python');
    if (pythonExtension?.isActive) {
        pythonExtensionPath = pythonExtension.exports?.settings?.getExecutionDetails?.()?.execCommand?.[0];
    }

    // Configured path takes precedence, then Python extension
    const configuredPath = config.get<string>('pythonPath');
    const effectivePythonPath = configuredPath || pythonExtensionPath;

    return {
        env: process.env as Record<string, string | undefined>,
        homeDir: process.env.HOME,
        workspaceRoot: workspaceFolders?.[0]?.uri.fsPath,
        configuredPythonPath: effectivePythonPath,
    };
}

/**
 * Start the LSP client and connect to the Python LSP server.
 */
export async function startLanguageClient(context: vscode.ExtensionContext): Promise<void> {
    const channel = getOutputChannel();

    channel.appendLine('='.repeat(60));
    channel.appendLine('Dazzle Language Server Starting...');
    channel.appendLine('This channel shows LSP messages (hover, completions, diagnostics)');
    channel.appendLine(`Timestamp: ${new Date().toISOString()}`);
    channel.appendLine('='.repeat(60));

    // Find a Python with dazzle.lsp installed using the core discovery logic
    const env = buildEnvironment();
    channel.appendLine('');
    channel.appendLine('Searching for Python with dazzle.lsp installed...');

    const discoveryResult = await findWorkingPython(env, nodeFileSystem, nodeProcessRunner, {
        timeoutMs: 5000,
    });

    // Cache the result
    cachedDiscoveryResult = discoveryResult;

    // Log discovery results
    channel.appendLine('');
    channel.appendLine(formatDiscoveryResult(discoveryResult));

    if (!discoveryResult.pythonPath) {
        channel.appendLine('');
        channel.appendLine('To enable LSP features:');
        channel.appendLine('  1. Install dazzle: pip install dazzle[lsp]');
        channel.appendLine('  2. Or for development: pip install -e /path/to/dazzle[lsp]');
        channel.appendLine('  3. Or set dazzle.pythonPath in VS Code settings');
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

    const pythonPath = discoveryResult.pythonPath;
    channel.appendLine('');

    // Server options: spawn the Python LSP server
    // Note: Use 'dazzle.lsp' (not 'dazzle.lsp.server') to avoid double module loading
    const serverOptions: ServerOptions = {
        command: pythonPath,
        args: ['-m', 'dazzle.lsp'],
        transport: TransportKind.stdio,
        options: {
            env: {
                ...process.env,
                // Inherit existing PYTHONPATH without modification
                // Development installations should set PYTHONPATH themselves
            }
        }
    };

    channel.appendLine(`Starting LSP server: ${pythonPath} -m dazzle.lsp`);

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
 * Get the cached Python path (for backwards compatibility).
 * @deprecated Use getDiscoveryResult() instead for full details.
 */
export function getPythonPath(): string {
    if (cachedDiscoveryResult?.pythonPath) {
        return cachedDiscoveryResult.pythonPath;
    }
    // Fallback for backwards compatibility
    return 'python3';
}

/**
 * Get the full discovery result (for diagnostics/debugging).
 */
export function getDiscoveryResult(): DiscoveryResult | null {
    return cachedDiscoveryResult;
}

/**
 * Check if the DAZZLE LSP server is available.
 * This now uses the cached result from discovery.
 */
export async function checkLspServerAvailable(): Promise<boolean> {
    if (cachedDiscoveryResult) {
        return cachedDiscoveryResult.pythonPath !== null;
    }

    // If not cached, run discovery
    const env = buildEnvironment();
    const result = await findWorkingPython(env, nodeFileSystem, nodeProcessRunner);
    cachedDiscoveryResult = result;
    return result.pythonPath !== null;
}

/**
 * Force re-discovery of Python (useful if user installs dazzle after extension starts).
 */
export async function rediscoverPython(): Promise<DiscoveryResult> {
    cachedDiscoveryResult = null;
    const env = buildEnvironment();
    const result = await findWorkingPython(env, nodeFileSystem, nodeProcessRunner);
    cachedDiscoveryResult = result;
    return result;
}
