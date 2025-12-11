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
    const channel = getOutputChannel();

    channel.appendLine('='.repeat(60));
    channel.appendLine('Dazzle Language Server Starting...');
    channel.appendLine('This channel shows LSP messages (hover, completions, diagnostics)');
    channel.appendLine(`Timestamp: ${new Date().toISOString()}`);
    channel.appendLine('='.repeat(60));

    // Find a Python with dazzle installed (checks multiple candidates)
    const isAvailable = await checkLspServerAvailable();
    const pythonPath = getPythonPath(); // Gets the cached result from checkLspServerAvailable

    if (!isAvailable) {
        channel.appendLine('');
        channel.appendLine('To enable LSP features:');
        channel.appendLine('  1. Install dazzle: pip install dazzle');
        channel.appendLine('  2. Or for development: pip install -e /path/to/dazzle');
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

// Cache the discovered Python path for the session
let cachedPythonPath: string | null = null;

/**
 * Try to get Python path from the dazzle CLI (works for Homebrew users).
 * Returns null if dazzle CLI is not available or doesn't report Python path.
 */
function getPythonFromDazzleCli(): string | null {
    try {
        const child_process = require('child_process');
        const fs = require('fs');

        // Try to find dazzle CLI
        const dazzlePaths = [
            '/opt/homebrew/bin/dazzle',
            '/usr/local/bin/dazzle',
        ];

        for (const dazzlePath of dazzlePaths) {
            if (!fs.existsSync(dazzlePath)) {
                continue;
            }

            // Read the wrapper script to extract DAZZLE_PYTHON
            const content = fs.readFileSync(dazzlePath, 'utf8');
            const match = content.match(/export DAZZLE_PYTHON="([^"]+)"/);
            if (match && match[1]) {
                const pythonPath = match[1];
                if (fs.existsSync(pythonPath)) {
                    return pythonPath;
                }
            }
        }
    } catch {
        // Ignore errors - this is just a discovery mechanism
    }
    return null;
}

/**
 * Find Homebrew Cellar dazzle Python paths.
 * Homebrew installs Python virtualenv at /opt/homebrew/Cellar/dazzle/VERSION/libexec/bin/python
 */
function getHomebrewDazzlePythonPaths(): string[] {
    const paths: string[] = [];
    try {
        const fs = require('fs');
        const cellarPaths = [
            '/opt/homebrew/Cellar/dazzle',  // Apple Silicon
            '/usr/local/Cellar/dazzle',      // Intel Mac
        ];

        for (const cellarPath of cellarPaths) {
            if (!fs.existsSync(cellarPath)) {
                continue;
            }

            // List version directories
            const versions = fs.readdirSync(cellarPath);
            for (const version of versions) {
                const pythonPath = `${cellarPath}/${version}/libexec/bin/python`;
                if (fs.existsSync(pythonPath)) {
                    paths.push(pythonPath);
                }
            }
        }
    } catch {
        // Ignore errors - directory might not exist
    }
    return paths;
}

/**
 * Get candidate Python paths to try, in priority order.
 */
function getPythonCandidates(): string[] {
    const candidates: string[] = [];
    const seen = new Set<string>();

    const addCandidate = (path: string | undefined | null) => {
        if (path && path.trim() !== '' && !seen.has(path)) {
            seen.add(path);
            candidates.push(path);
        }
    };

    // 1. Explicit configuration (highest priority)
    const config = vscode.workspace.getConfiguration('dazzle');
    addCandidate(config.get<string>('pythonPath'));

    // 2. Environment variable
    addCandidate(process.env.DAZZLE_PYTHON);

    // 3. Homebrew dazzle wrapper script (extracts DAZZLE_PYTHON from wrapper)
    // This is the most reliable way to find Python for Homebrew users
    addCandidate(getPythonFromDazzleCli());

    // 4. Homebrew Cellar paths (direct lookup for Apple Silicon and Intel Macs)
    for (const homebrewPath of getHomebrewDazzlePythonPaths()) {
        addCandidate(homebrewPath);
    }

    // 5. Python extension's active interpreter
    const pythonExtension = vscode.extensions.getExtension('ms-python.python');
    if (pythonExtension && pythonExtension.isActive) {
        const pythonPath = pythonExtension.exports?.settings?.getExecutionDetails?.()?.execCommand?.[0];
        addCandidate(pythonPath);
    }

    // 6. pyenv shims (common for developers)
    const home = process.env.HOME;
    if (home) {
        addCandidate(`${home}/.pyenv/shims/python3`);
        addCandidate(`${home}/.pyenv/shims/python`);
    }

    // 7. Common virtual environment locations relative to workspace
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (workspaceFolders && workspaceFolders.length > 0) {
        const wsRoot = workspaceFolders[0].uri.fsPath;
        addCandidate(`${wsRoot}/.venv/bin/python`);
        addCandidate(`${wsRoot}/venv/bin/python`);
        addCandidate(`${wsRoot}/.venv/bin/python3`);
        addCandidate(`${wsRoot}/venv/bin/python3`);
    }

    // 8. System Python (fallback)
    addCandidate('python3');
    addCandidate('python');

    // 9. Common macOS/Linux paths
    addCandidate('/usr/local/bin/python3');
    addCandidate('/opt/homebrew/bin/python3');
    addCandidate('/usr/bin/python3');

    return candidates;
}

/**
 * Check if a Python path can import dazzle.lsp.
 */
async function canImportDazzle(pythonPath: string): Promise<boolean> {
    return new Promise((resolve) => {
        const child_process = require('child_process');
        const proc = child_process.spawn(pythonPath, ['-c', 'import dazzle.lsp'], {
            stdio: 'pipe',
        });

        proc.on('close', (code: number | null) => {
            resolve(code === 0);
        });

        proc.on('error', () => {
            resolve(false);
        });

        // Timeout after 2 seconds
        setTimeout(() => {
            proc.kill();
            resolve(false);
        }, 2000);
    });
}

/**
 * Find a Python interpreter that has dazzle installed.
 *
 * Tries multiple candidate paths and returns the first one that works.
 * Results are cached for the session.
 */
async function findPythonWithDazzle(channel: vscode.OutputChannel): Promise<string | null> {
    // Return cached result if available
    if (cachedPythonPath !== null) {
        return cachedPythonPath;
    }

    const candidates = getPythonCandidates();
    channel.appendLine(`Searching for Python with dazzle.lsp installed...`);
    channel.appendLine(`Candidates: ${candidates.slice(0, 5).join(', ')}${candidates.length > 5 ? '...' : ''}`);

    for (const candidate of candidates) {
        const hasModule = await canImportDazzle(candidate);
        if (hasModule) {
            channel.appendLine(`✅ Found dazzle.lsp in: ${candidate}`);
            cachedPythonPath = candidate;
            return candidate;
        }
    }

    channel.appendLine(`❌ No Python with dazzle.lsp found`);
    return null;
}

/**
 * Get the Python interpreter path (for backwards compatibility).
 * Returns the first candidate, use findPythonWithDazzle() for smart detection.
 */
function getPythonPath(): string {
    if (cachedPythonPath) {
        return cachedPythonPath;
    }
    const candidates = getPythonCandidates();
    return candidates[0] || 'python3';
}

/**
 * Check if the DAZZLE LSP server is available.
 * This now uses smart detection to find a Python with dazzle installed.
 */
export async function checkLspServerAvailable(): Promise<boolean> {
    const channel = getOutputChannel();
    const pythonPath = await findPythonWithDazzle(channel);
    return pythonPath !== null;
}
