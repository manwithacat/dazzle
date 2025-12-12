/**
 * Python Discovery - Core Logic
 *
 * This module contains the pure business logic for finding a Python interpreter
 * with dazzle.lsp installed. It has NO dependencies on the vscode module,
 * making it fully testable without VS Code.
 *
 * Architecture:
 * - All external dependencies (filesystem, process spawning) are injected via interfaces
 * - The module exports pure functions that can be tested with mock implementations
 */

// ============================================================================
// Interfaces (for dependency injection)
// ============================================================================

/**
 * Interface for spawning processes.
 * Production uses child_process.spawn, tests can use mocks.
 */
export interface ProcessRunner {
    spawn(command: string, args: string[], options?: SpawnOptions): Promise<SpawnResult>;
}

export interface SpawnOptions {
    timeout?: number;
    env?: Record<string, string | undefined>;
}

export interface SpawnResult {
    exitCode: number | null;
    stdout: string;
    stderr: string;
    timedOut: boolean;
}

/**
 * Interface for filesystem operations.
 * Production uses Node's fs module, tests can use in-memory filesystem.
 */
export interface FileSystem {
    exists(path: string): boolean;
    readFile(path: string): string | null;
    readDir(path: string): string[];
}

/**
 * Interface for environment/configuration.
 * Production reads from process.env and vscode config, tests use plain objects.
 */
export interface Environment {
    env: Record<string, string | undefined>;
    homeDir: string | undefined;
    workspaceRoot: string | undefined;
    configuredPythonPath: string | undefined;
}

// ============================================================================
// Types
// ============================================================================

export interface PythonCandidate {
    path: string;
    source: string;
    priority: number;
}

export interface DiscoveryResult {
    pythonPath: string | null;
    candidates: PythonCandidate[];
    testedCandidates: Array<{
        candidate: PythonCandidate;
        success: boolean;
        error?: string;
    }>;
}

// ============================================================================
// Core Discovery Logic
// ============================================================================

/**
 * Get candidate Python paths to try, in priority order.
 *
 * Priority order:
 * 1. Explicit configuration (highest)
 * 2. DAZZLE_PYTHON environment variable
 * 3. Homebrew dazzle wrapper (extracts DAZZLE_PYTHON)
 * 4. Homebrew Cellar direct paths
 * 5. VS Code Python extension's interpreter (passed via config)
 * 6. pyenv shims
 * 7. Workspace virtual environments
 * 8. System Python (lowest)
 */
export function getPythonCandidates(env: Environment, fs: FileSystem): PythonCandidate[] {
    const candidates: PythonCandidate[] = [];
    const seen = new Set<string>();

    const addCandidate = (path: string | undefined | null, source: string, priority: number) => {
        if (path && path.trim() !== '' && !seen.has(path)) {
            // Only add if path exists (for non-bare commands like 'python3')
            const isBareCommand = !path.includes('/');
            if (isBareCommand || fs.exists(path)) {
                seen.add(path);
                candidates.push({ path, source, priority });
            }
        }
    };

    // 1. Explicit configuration (highest priority)
    addCandidate(env.configuredPythonPath, 'VS Code setting (dazzle.pythonPath)', 1);

    // 2. Environment variable
    addCandidate(env.env.DAZZLE_PYTHON, 'DAZZLE_PYTHON environment variable', 2);

    // 3. Homebrew wrapper extraction
    const homebrewPython = extractPythonFromHomebrewWrapper(fs);
    if (homebrewPython) {
        addCandidate(homebrewPython, 'Homebrew dazzle wrapper', 3);
    }

    // 4. Homebrew Cellar direct lookup
    for (const cellarPath of getHomebrewCellarPaths(fs)) {
        addCandidate(cellarPath.path, cellarPath.source, 4);
    }

    // 5. pyenv shims
    if (env.homeDir) {
        addCandidate(`${env.homeDir}/.pyenv/shims/python3`, 'pyenv shim', 6);
        addCandidate(`${env.homeDir}/.pyenv/shims/python`, 'pyenv shim', 6);
    }

    // 6. Workspace virtual environments
    if (env.workspaceRoot) {
        addCandidate(`${env.workspaceRoot}/.venv/bin/python`, 'workspace .venv', 7);
        addCandidate(`${env.workspaceRoot}/venv/bin/python`, 'workspace venv', 7);
        addCandidate(`${env.workspaceRoot}/.venv/bin/python3`, 'workspace .venv', 7);
        addCandidate(`${env.workspaceRoot}/venv/bin/python3`, 'workspace venv', 7);
    }

    // 7. System Python (fallback)
    addCandidate('python3', 'system PATH', 8);
    addCandidate('python', 'system PATH', 8);

    // 8. Common macOS/Linux paths
    addCandidate('/usr/local/bin/python3', 'system (/usr/local)', 9);
    addCandidate('/opt/homebrew/bin/python3', 'Homebrew Python', 9);
    addCandidate('/usr/bin/python3', 'system (/usr)', 9);

    // Sort by priority
    candidates.sort((a, b) => a.priority - b.priority);

    return candidates;
}

/**
 * Extract DAZZLE_PYTHON from Homebrew wrapper script.
 */
function extractPythonFromHomebrewWrapper(fs: FileSystem): string | null {
    const wrapperPaths = [
        '/opt/homebrew/bin/dazzle',
        '/usr/local/bin/dazzle',
    ];

    for (const wrapperPath of wrapperPaths) {
        if (!fs.exists(wrapperPath)) {
            continue;
        }

        const content = fs.readFile(wrapperPath);
        if (!content) {
            continue;
        }

        const match = content.match(/export DAZZLE_PYTHON="([^"]+)"/);
        if (match?.[1] && fs.exists(match[1])) {
            return match[1];
        }
    }

    return null;
}

/**
 * Get Python paths from Homebrew Cellar.
 */
function getHomebrewCellarPaths(fs: FileSystem): Array<{ path: string; source: string }> {
    const paths: Array<{ path: string; source: string }> = [];
    const cellarRoots = [
        '/opt/homebrew/Cellar/dazzle',  // Apple Silicon
        '/usr/local/Cellar/dazzle',      // Intel Mac
    ];

    for (const cellarRoot of cellarRoots) {
        if (!fs.exists(cellarRoot)) {
            continue;
        }

        try {
            const versions = fs.readDir(cellarRoot);
            for (const version of versions) {
                const pythonPath = `${cellarRoot}/${version}/libexec/bin/python`;
                if (fs.exists(pythonPath)) {
                    paths.push({
                        path: pythonPath,
                        source: `Homebrew Cellar (${version})`,
                    });
                }
            }
        } catch {
            // Ignore errors reading directory
        }
    }

    return paths;
}

/**
 * Check if a Python interpreter can import dazzle.lsp.
 */
export async function canImportDazzleLsp(
    pythonPath: string,
    runner: ProcessRunner,
    timeoutMs: number = 5000
): Promise<{ success: boolean; error?: string }> {
    try {
        const result = await runner.spawn(pythonPath, ['-c', 'import dazzle.lsp'], {
            timeout: timeoutMs,
        });

        if (result.timedOut) {
            return { success: false, error: 'timeout' };
        }

        if (result.exitCode === 0) {
            return { success: true };
        }

        // Extract useful error message
        const stderr = result.stderr;
        if (stderr.includes('ModuleNotFoundError')) {
            const match = stderr.match(/No module named '([^']+)'/);
            return {
                success: false,
                error: match ? `missing module: ${match[1]}` : 'module not found',
            };
        }

        return { success: false, error: `exit code ${result.exitCode}` };
    } catch (err) {
        return {
            success: false,
            error: err instanceof Error ? err.message : 'unknown error',
        };
    }
}

/**
 * Find a working Python interpreter with dazzle.lsp installed.
 *
 * Tries candidates in priority order and returns the first one that works.
 */
export async function findWorkingPython(
    env: Environment,
    fs: FileSystem,
    runner: ProcessRunner,
    options: { timeoutMs?: number } = {}
): Promise<DiscoveryResult> {
    const { timeoutMs = 5000 } = options;
    const candidates = getPythonCandidates(env, fs);
    const testedCandidates: DiscoveryResult['testedCandidates'] = [];

    for (const candidate of candidates) {
        const result = await canImportDazzleLsp(candidate.path, runner, timeoutMs);
        testedCandidates.push({
            candidate,
            success: result.success,
            error: result.error,
        });

        if (result.success) {
            return {
                pythonPath: candidate.path,
                candidates,
                testedCandidates,
            };
        }
    }

    return {
        pythonPath: null,
        candidates,
        testedCandidates,
    };
}

/**
 * Format discovery results for logging/display.
 */
export function formatDiscoveryResult(result: DiscoveryResult): string {
    const lines: string[] = [];

    lines.push('Python Discovery Results:');
    lines.push('');

    if (result.pythonPath) {
        lines.push(`✅ Found working Python: ${result.pythonPath}`);
    } else {
        lines.push('❌ No Python with dazzle.lsp found');
    }

    lines.push('');
    lines.push('Candidates tested:');

    for (const tested of result.testedCandidates) {
        const status = tested.success ? '✓' : '✗';
        const error = tested.error ? ` (${tested.error})` : '';
        lines.push(`  ${status} ${tested.candidate.path} [${tested.candidate.source}]${error}`);
    }

    if (!result.pythonPath) {
        lines.push('');
        lines.push('To fix, install dazzle with LSP support:');
        lines.push('  pip install dazzle[lsp]');
    }

    return lines.join('\n');
}
