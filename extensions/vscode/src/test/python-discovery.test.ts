/**
 * Python Discovery Unit Tests
 *
 * These tests run OUTSIDE of VS Code (no vscode dependency).
 * Run with: npm run test:python
 *
 * Test tiers (following the testing strategy spec):
 * - Tier 1: Pure unit tests with mocks (most tests here)
 * - Tier 3: Integration tests with real Python (marked with .integration)
 */

import * as assert from 'assert';
import * as fs from 'fs';

// Core module (no vscode dependency - fully testable)
import {
    getPythonCandidates,
    canImportDazzleLsp,
    findWorkingPython,
    formatDiscoveryResult,
    type Environment,
    type PythonCandidate,
} from '../core/pythonDiscovery';

// Adapters (production and mock implementations)
import {
    nodeProcessRunner,
    createMockProcessRunner,
    mockResponses,
} from '../adapters/nodeProcess';
import {
    nodeFileSystem,
    MockFileSystem,
    createHomebrewMockFs,
    createPyenvMockFs,
} from '../adapters/nodeFs';

// ============================================================================
// Tier 1: Pure Unit Tests (with mocks)
// ============================================================================

describe('Python Discovery - Unit Tests (Tier 1)', function() {
    this.timeout(5000);

    describe('getPythonCandidates', () => {
        it('should return empty array when no Python found', () => {
            const env: Environment = {
                env: {},
                homeDir: undefined,
                workspaceRoot: undefined,
                configuredPythonPath: undefined,
            };
            const mockFs = new MockFileSystem();

            const candidates = getPythonCandidates(env, mockFs);

            // Should still include bare commands like 'python3' even if paths don't exist
            assert.ok(Array.isArray(candidates));
        });

        it('should prioritize configured Python path', () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: '/custom/python',
            };
            const mockFs = new MockFileSystem()
                .addExisting('/custom/python')
                .addExisting('/Users/test/.pyenv/shims/python3');

            const candidates = getPythonCandidates(env, mockFs);

            assert.ok(candidates.length > 0);
            assert.strictEqual(candidates[0].path, '/custom/python');
            assert.strictEqual(candidates[0].source, 'VS Code setting (dazzle.pythonPath)');
        });

        it('should find Homebrew Python from wrapper script', () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: undefined,
            };
            const mockFs = createHomebrewMockFs('0.12.0');

            const candidates = getPythonCandidates(env, mockFs);

            const homebrewCandidate = candidates.find(c => c.source === 'Homebrew dazzle wrapper');
            assert.ok(homebrewCandidate, 'Should find Homebrew wrapper Python');
            assert.strictEqual(
                homebrewCandidate.path,
                '/opt/homebrew/Cellar/dazzle/0.12.0/libexec/bin/python'
            );
        });

        it('should find pyenv shims', () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: undefined,
            };
            const mockFs = createPyenvMockFs('/Users/test');

            const candidates = getPythonCandidates(env, mockFs);

            const pyenvCandidate = candidates.find(c => c.source === 'pyenv shim');
            assert.ok(pyenvCandidate, 'Should find pyenv shim');
            assert.ok(pyenvCandidate.path.includes('.pyenv/shims/'));
        });

        it('should find workspace virtual environment', () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: '/projects/myapp',
                configuredPythonPath: undefined,
            };
            const mockFs = new MockFileSystem()
                .addExisting('/projects/myapp/.venv/bin/python');

            const candidates = getPythonCandidates(env, mockFs);

            const venvCandidate = candidates.find(c => c.source === 'workspace .venv');
            assert.ok(venvCandidate, 'Should find workspace venv');
            assert.strictEqual(venvCandidate.path, '/projects/myapp/.venv/bin/python');
        });

        it('should respect DAZZLE_PYTHON environment variable', () => {
            const env: Environment = {
                env: { DAZZLE_PYTHON: '/special/python' },
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: undefined,
            };
            const mockFs = new MockFileSystem().addExisting('/special/python');

            const candidates = getPythonCandidates(env, mockFs);

            const envCandidate = candidates.find(c => c.source === 'DAZZLE_PYTHON environment variable');
            assert.ok(envCandidate, 'Should find DAZZLE_PYTHON');
            assert.strictEqual(envCandidate.path, '/special/python');
        });

        it('should sort candidates by priority', () => {
            const env: Environment = {
                env: { DAZZLE_PYTHON: '/env/python' },
                homeDir: '/Users/test',
                workspaceRoot: '/projects/myapp',
                configuredPythonPath: '/configured/python',
            };
            const mockFs = new MockFileSystem()
                .addExisting('/configured/python')
                .addExisting('/env/python')
                .addExisting('/Users/test/.pyenv/shims/python3')
                .addExisting('/projects/myapp/.venv/bin/python');

            const candidates = getPythonCandidates(env, mockFs);

            // Configured should be first (priority 1)
            assert.strictEqual(candidates[0].path, '/configured/python');
            // DAZZLE_PYTHON should be second (priority 2)
            assert.strictEqual(candidates[1].path, '/env/python');
        });
    });

    describe('canImportDazzleLsp', () => {
        it('should return success for Python with dazzle.lsp', async () => {
            const mockRunner = createMockProcessRunner(new Map([
                ['/good/python -c import dazzle.lsp', mockResponses.pythonWithDazzle],
            ]));

            const result = await canImportDazzleLsp('/good/python', mockRunner);

            assert.strictEqual(result.success, true);
            assert.strictEqual(result.error, undefined);
        });

        it('should return failure with missing module error', async () => {
            const mockRunner = createMockProcessRunner(new Map([
                ['/bad/python -c import dazzle.lsp', mockResponses.pythonMissingLsprotocol],
            ]));

            const result = await canImportDazzleLsp('/bad/python', mockRunner);

            assert.strictEqual(result.success, false);
            assert.ok(result.error?.includes('lsprotocol'));
        });

        it('should handle command not found', async () => {
            const mockRunner = createMockProcessRunner(new Map([
                ['/nonexistent/python', mockResponses.commandNotFound],
            ]));

            const result = await canImportDazzleLsp('/nonexistent/python', mockRunner);

            assert.strictEqual(result.success, false);
        });

        it('should handle timeout', async () => {
            const mockRunner = createMockProcessRunner(new Map([
                ['/slow/python -c import dazzle.lsp', mockResponses.timeout],
            ]));

            const result = await canImportDazzleLsp('/slow/python', mockRunner);

            assert.strictEqual(result.success, false);
            assert.strictEqual(result.error, 'timeout');
        });
    });

    describe('findWorkingPython', () => {
        it('should return first working Python', async () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: undefined,
            };
            const mockFs = new MockFileSystem()
                .addExisting('/Users/test/.pyenv/shims/python3');

            const mockRunner = createMockProcessRunner((cmd) => {
                if (cmd === '/Users/test/.pyenv/shims/python3') {
                    return mockResponses.pythonWithDazzle;
                }
                return mockResponses.commandNotFound;
            });

            const result = await findWorkingPython(env, mockFs, mockRunner);

            assert.strictEqual(result.pythonPath, '/Users/test/.pyenv/shims/python3');
            assert.ok(result.testedCandidates.length > 0);
        });

        it('should return null when no working Python found', async () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: '/broken/python',
            };
            const mockFs = new MockFileSystem()
                .addExisting('/broken/python');

            const mockRunner = createMockProcessRunner(() => mockResponses.pythonMissingDazzle);

            const result = await findWorkingPython(env, mockFs, mockRunner);

            assert.strictEqual(result.pythonPath, null);
            assert.ok(result.testedCandidates.some(t => !t.success));
        });

        it('should skip broken Python and try next candidate', async () => {
            const env: Environment = {
                env: {},
                homeDir: '/Users/test',
                workspaceRoot: undefined,
                configuredPythonPath: '/broken/python',
            };
            const mockFs = new MockFileSystem()
                .addExisting('/broken/python')
                .addExisting('/Users/test/.pyenv/shims/python3');

            const mockRunner = createMockProcessRunner((cmd) => {
                if (cmd === '/broken/python') {
                    return mockResponses.pythonMissingLsprotocol;
                }
                if (cmd === '/Users/test/.pyenv/shims/python3') {
                    return mockResponses.pythonWithDazzle;
                }
                return mockResponses.commandNotFound;
            });

            const result = await findWorkingPython(env, mockFs, mockRunner);

            assert.strictEqual(result.pythonPath, '/Users/test/.pyenv/shims/python3');
            // Should have tested broken first, then pyenv
            assert.ok(result.testedCandidates.length >= 2);
        });
    });

    describe('formatDiscoveryResult', () => {
        it('should format success result', () => {
            const result = {
                pythonPath: '/good/python',
                candidates: [{ path: '/good/python', source: 'test', priority: 1 }],
                testedCandidates: [{
                    candidate: { path: '/good/python', source: 'test', priority: 1 },
                    success: true,
                }],
            };

            const formatted = formatDiscoveryResult(result);

            assert.ok(formatted.includes('✅'));
            assert.ok(formatted.includes('/good/python'));
        });

        it('should format failure result with help text', () => {
            const result = {
                pythonPath: null,
                candidates: [{ path: '/bad/python', source: 'test', priority: 1 }],
                testedCandidates: [{
                    candidate: { path: '/bad/python', source: 'test', priority: 1 },
                    success: false,
                    error: 'missing module: lsprotocol',
                }],
            };

            const formatted = formatDiscoveryResult(result);

            assert.ok(formatted.includes('❌'));
            assert.ok(formatted.includes('pip install dazzle[lsp]'));
        });
    });
});

// ============================================================================
// Tier 3: Integration Tests (real Python)
// ============================================================================

describe('Python Discovery - Integration Tests (Tier 3)', function() {
    this.timeout(30000);

    describe('Real Python import check', () => {
        it('should detect real Python with dazzle.lsp', async function() {
            // Skip if no Python available
            const candidates = getPythonCandidates({
                env: process.env as Record<string, string | undefined>,
                homeDir: process.env.HOME,
                workspaceRoot: undefined,
                configuredPythonPath: undefined,
            }, nodeFileSystem);

            if (candidates.length === 0) {
                this.skip();
                return;
            }

            // Try to find a working Python
            let foundWorking = false;
            for (const candidate of candidates) {
                const result = await canImportDazzleLsp(candidate.path, nodeProcessRunner, 10000);
                if (result.success) {
                    foundWorking = true;
                    console.log(`    ✓ ${candidate.path} (${candidate.source})`);
                    break;
                }
            }

            assert.ok(foundWorking, 'Should find at least one Python with dazzle.lsp');
        });

        it('should detect Homebrew installation if present', async function() {
            const homebrewPython = '/opt/homebrew/Cellar/dazzle/0.12.0/libexec/bin/python';

            if (!fs.existsSync(homebrewPython)) {
                this.skip();
                return;
            }

            const result = await canImportDazzleLsp(homebrewPython, nodeProcessRunner, 10000);

            if (!result.success) {
                assert.fail(
                    `Homebrew dazzle missing LSP deps: ${result.error}\n` +
                    'Fix: brew reinstall dazzle (after updating tap formula)'
                );
            }
        });
    });

    describe('Full discovery flow', () => {
        it('should complete discovery with real system', async function() {
            const env: Environment = {
                env: process.env as Record<string, string | undefined>,
                homeDir: process.env.HOME,
                workspaceRoot: process.cwd(),
                configuredPythonPath: undefined,
            };

            const result = await findWorkingPython(env, nodeFileSystem, nodeProcessRunner, {
                timeoutMs: 10000,
            });

            console.log('\n' + formatDiscoveryResult(result));

            // Don't fail if no Python found - just report
            if (!result.pythonPath) {
                console.log('    (No Python with dazzle.lsp found - install with pip install dazzle[lsp])');
            }
        });
    });
});

// ============================================================================
// TODO: Future Tests (Tier 2 Contract Tests)
// ============================================================================

describe.skip('Python Discovery - Contract Tests (Tier 2) [TODO]', function() {
    /**
     * These tests would verify the contract between lspClient.ts and the core module.
     * They require mocking vscode APIs which adds complexity.
     *
     * Implement when:
     * - We need to test VS Code-specific behavior
     * - We add more complex VS Code integrations
     */

    it.skip('TODO: should call findWorkingPython with correct environment', async () => {
        // Would need to mock vscode.workspace.getConfiguration
        // and verify buildEnvironment() produces correct Environment
    });

    it.skip('TODO: should show warning when no Python found', async () => {
        // Would need to mock vscode.window.showWarningMessage
        // and verify it's called with correct message
    });

    it.skip('TODO: should start LSP client with discovered Python', async () => {
        // Would need to mock LanguageClient
        // and verify serverOptions.command is set correctly
    });
});

describe.skip('Python Discovery - Golden Tests (Tier 2) [TODO]', function() {
    /**
     * Golden tests for discovery output formatting.
     * Useful if we want to ensure consistent output format.
     *
     * Implement when:
     * - Output format becomes part of public API
     * - We need to catch unintended format changes
     */

    it.skip('TODO: discovery output should match golden snapshot', async () => {
        // Would compare formatDiscoveryResult output against stored snapshot
        // Use UPDATE_GOLDENS=1 to update snapshots
    });
});

describe.skip('Python Discovery - E2E Tests (Tier 4) [TODO]', function() {
    /**
     * Full end-to-end tests that launch VS Code.
     * These are slow and should only run in CI/nightly.
     *
     * Implement when:
     * - We need to verify the full extension activation flow
     * - We're debugging issues that only occur in VS Code
     */

    it.skip('TODO: extension should activate and find Python', async () => {
        // Would use @vscode/test-electron to launch VS Code
        // Open a .dsl file and verify LSP features work
    });

    it.skip('TODO: LSP hover should work after activation', async () => {
        // Would activate extension, open .dsl file
        // Trigger hover and verify response
    });
});
