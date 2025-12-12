/**
 * Node.js Process Runner Adapter
 *
 * Production implementation of ProcessRunner using child_process.
 * This adapter wraps Node's spawn() in the ProcessRunner interface,
 * allowing the core logic to be tested with mock implementations.
 */

import * as child_process from 'child_process';
import type { ProcessRunner, SpawnOptions, SpawnResult } from '../core/pythonDiscovery';

/**
 * Production process runner using Node.js child_process.
 */
export const nodeProcessRunner: ProcessRunner = {
    async spawn(command: string, args: string[], options: SpawnOptions = {}): Promise<SpawnResult> {
        const { timeout = 30000, env } = options;

        return new Promise((resolve) => {
            let stdout = '';
            let stderr = '';
            let timedOut = false;
            let resolved = false;

            const spawnOptions: child_process.SpawnOptions = {
                stdio: ['pipe', 'pipe', 'pipe'],
            };

            if (env) {
                spawnOptions.env = { ...process.env, ...env };
            }

            const proc = child_process.spawn(command, args, spawnOptions);

            proc.stdout?.on('data', (data: Buffer) => {
                stdout += data.toString();
            });

            proc.stderr?.on('data', (data: Buffer) => {
                stderr += data.toString();
            });

            const timeoutHandle = setTimeout(() => {
                if (!resolved) {
                    timedOut = true;
                    proc.kill('SIGTERM');
                    // Give it a moment to terminate gracefully
                    setTimeout(() => {
                        if (!resolved) {
                            proc.kill('SIGKILL');
                        }
                    }, 1000);
                }
            }, timeout);

            proc.on('close', (code: number | null) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timeoutHandle);
                    resolve({
                        exitCode: code,
                        stdout,
                        stderr,
                        timedOut,
                    });
                }
            });

            proc.on('error', (err: Error) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timeoutHandle);
                    resolve({
                        exitCode: null,
                        stdout,
                        stderr: err.message,
                        timedOut: false,
                    });
                }
            });
        });
    },
};

/**
 * Create a mock process runner for testing.
 *
 * @param responses Map of command patterns to mock responses
 */
export function createMockProcessRunner(
    responses: Map<string, SpawnResult> | ((cmd: string, args: string[]) => SpawnResult)
): ProcessRunner {
    return {
        async spawn(command: string, args: string[]): Promise<SpawnResult> {
            const key = `${command} ${args.join(' ')}`;

            if (typeof responses === 'function') {
                return responses(command, args);
            }

            // Try exact match first
            if (responses.has(key)) {
                return responses.get(key)!;
            }

            // Try command-only match
            if (responses.has(command)) {
                return responses.get(command)!;
            }

            // Default: command not found
            return {
                exitCode: null,
                stdout: '',
                stderr: `spawn ${command} ENOENT`,
                timedOut: false,
            };
        },
    };
}

/**
 * Preset mock responses for common test scenarios.
 */
export const mockResponses = {
    /** Python that has dazzle.lsp installed */
    pythonWithDazzle: {
        exitCode: 0,
        stdout: '',
        stderr: 'INFO:pygls.feature_manager:Registered builtin feature exit\n',
        timedOut: false,
    } as SpawnResult,

    /** Python missing lsprotocol */
    pythonMissingLsprotocol: {
        exitCode: 1,
        stdout: '',
        stderr: "ModuleNotFoundError: No module named 'lsprotocol'\n",
        timedOut: false,
    } as SpawnResult,

    /** Python missing dazzle entirely */
    pythonMissingDazzle: {
        exitCode: 1,
        stdout: '',
        stderr: "ModuleNotFoundError: No module named 'dazzle'\n",
        timedOut: false,
    } as SpawnResult,

    /** Command not found */
    commandNotFound: {
        exitCode: null,
        stdout: '',
        stderr: 'spawn python3 ENOENT',
        timedOut: false,
    } as SpawnResult,

    /** Timeout */
    timeout: {
        exitCode: null,
        stdout: '',
        stderr: '',
        timedOut: true,
    } as SpawnResult,
};
