import * as vscode from 'vscode';
import * as child_process from 'child_process';
import * as path from 'path';

/**
 * Diagnostics Provider for DAZZLE DSL files
 *
 * Runs `dazzle check --json` (v0.8.0+ CLI) and parses JSON output to create diagnostics
 */

/**
 * JSON output format from `dazzle check --json`
 */
interface CheckResult {
    success: boolean;
    valid: boolean;
    modules?: Array<{
        name: string;
        path: string;
        entities: number;
        surfaces: number;
    }>;
    entities?: string[];
    surfaces?: string[];
    errors?: Array<{
        file: string;
        line: number;
        message: string;
        code: string;
    }>;
    warnings?: Array<{
        file: string;
        line: number;
        message: string;
        code: string;
    }>;
    __agent_hint?: string;
}

export class DazzleDiagnostics {
    private diagnosticCollection: vscode.DiagnosticCollection;
    private outputChannel: vscode.OutputChannel;

    constructor() {
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection('dazzle');
        this.outputChannel = vscode.window.createOutputChannel('Dazzle');
        // Show the output channel to ensure it's visible
        this.outputChannel.show(true);
        this.outputChannel.appendLine('DAZZLE extension initialized (v0.8.0)');
        this.outputChannel.appendLine('This channel shows output from DAZZLE CLI commands (check, build, test)');
    }

    /**
     * Run validation and update diagnostics
     */
    public async validateWorkspace(workspaceFolder: vscode.WorkspaceFolder): Promise<void> {
        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        this.outputChannel.appendLine(`Running validation in ${workspaceFolder.uri.fsPath}...`);

        try {
            const result = await this.runValidation(workspaceFolder.uri.fsPath, cliPath);
            this.processValidationOutput(result, workspaceFolder);
        } catch (error) {
            this.outputChannel.appendLine(`Validation error: ${error}`);
            vscode.window.showErrorMessage(`DAZZLE validation failed: ${error}`);
        }
    }

    /**
     * Run dazzle check --json command (v0.8.0+ CLI)
     */
    private runValidation(cwd: string, cliPath: string): Promise<string> {
        return new Promise((resolve, reject) => {
            // v0.8.0 CLI uses 'check --json' instead of 'validate --format vscode'
            const args = ['check', '--json'];

            this.outputChannel.appendLine(`Executing: ${cliPath} ${args.join(' ')}`);

            const childProcess = child_process.spawn(cliPath, args, {
                cwd,
                shell: process.platform === 'win32'
            });

            let stdout = '';
            let stderr = '';

            childProcess.stdout?.on('data', (data: Buffer) => {
                stdout += data.toString();
            });

            childProcess.stderr?.on('data', (data: Buffer) => {
                stderr += data.toString();
            });

            childProcess.on('close', (code: number | null) => {
                this.outputChannel.appendLine(`Validation completed with code ${code}`);
                // JSON output goes to stdout; stderr may have additional info
                if (stderr.trim()) {
                    this.outputChannel.appendLine(`stderr: ${stderr}`);
                }
                resolve(stdout);
            });

            childProcess.on('error', (error: Error) => {
                reject(new Error(`Failed to run DAZZLE CLI: ${error.message}`));
            });
        });
    }

    /**
     * Parse JSON validation output and create VS Code diagnostics
     */
    private processValidationOutput(output: string, workspaceFolder: vscode.WorkspaceFolder): void {
        // Clear existing diagnostics
        this.diagnosticCollection.clear();

        const diagnosticsMap = new Map<string, vscode.Diagnostic[]>();

        try {
            const result: CheckResult = JSON.parse(output);

            this.outputChannel.appendLine(`Valid: ${result.valid}`);
            if (result.entities) {
                this.outputChannel.appendLine(`Entities: ${result.entities.join(', ')}`);
            }
            if (result.surfaces) {
                this.outputChannel.appendLine(`Surfaces: ${result.surfaces.join(', ')}`);
            }

            // Process errors
            if (result.errors && result.errors.length > 0) {
                for (const error of result.errors) {
                    this.addDiagnostic(
                        diagnosticsMap,
                        workspaceFolder,
                        error.file,
                        error.line,
                        error.message,
                        error.code,
                        vscode.DiagnosticSeverity.Error
                    );
                }
            }

            // Process warnings
            if (result.warnings && result.warnings.length > 0) {
                for (const warning of result.warnings) {
                    this.addDiagnostic(
                        diagnosticsMap,
                        workspaceFolder,
                        warning.file,
                        warning.line,
                        warning.message,
                        warning.code,
                        vscode.DiagnosticSeverity.Warning
                    );
                }
            }

        } catch (parseError) {
            // Fallback: try to parse old-style line-by-line output for backwards compatibility
            this.outputChannel.appendLine(`JSON parse failed, trying legacy format: ${parseError}`);
            this.processLegacyOutput(output, workspaceFolder, diagnosticsMap);
        }

        // Set diagnostics for each file
        for (const [filePath, diagnostics] of diagnosticsMap) {
            const fileUri = vscode.Uri.file(filePath);
            this.diagnosticCollection.set(fileUri, diagnostics);
        }

        // Show summary in output
        const totalDiagnostics = Array.from(diagnosticsMap.values()).reduce((sum, arr) => sum + arr.length, 0);
        if (totalDiagnostics > 0) {
            this.outputChannel.appendLine(`Found ${totalDiagnostics} diagnostic(s)`);
        } else {
            this.outputChannel.appendLine('No issues found');
        }
    }

    /**
     * Add a diagnostic to the map
     */
    private addDiagnostic(
        diagnosticsMap: Map<string, vscode.Diagnostic[]>,
        workspaceFolder: vscode.WorkspaceFolder,
        file: string,
        line: number,
        message: string,
        code: string,
        severity: vscode.DiagnosticSeverity
    ): void {
        // Use line 1 if not specified, convert to 0-based
        const lineNum = Math.max(0, (line || 1) - 1);

        // Create VS Code diagnostic
        const range = new vscode.Range(
            new vscode.Position(lineNum, 0),
            new vscode.Position(lineNum, 1000) // Highlight the entire line
        );

        const diagnostic = new vscode.Diagnostic(range, message, severity);
        diagnostic.source = 'DAZZLE';
        diagnostic.code = code;

        // Resolve file path relative to workspace
        let filePath: string;
        if (file && file.trim() !== '') {
            filePath = path.isAbsolute(file)
                ? file
                : path.join(workspaceFolder.uri.fsPath, file);
        } else {
            // No file specified, use dazzle.toml as fallback
            filePath = path.join(workspaceFolder.uri.fsPath, 'dazzle.toml');
        }

        // Add to diagnostics map
        if (!diagnosticsMap.has(filePath)) {
            diagnosticsMap.set(filePath, []);
        }
        diagnosticsMap.get(filePath)!.push(diagnostic);
    }

    /**
     * Legacy output format parser (for backwards compatibility with old CLI)
     */
    private processLegacyOutput(
        output: string,
        workspaceFolder: vscode.WorkspaceFolder,
        diagnosticsMap: Map<string, vscode.Diagnostic[]>
    ): void {
        // Parse each line: file:line:col: severity: message
        const lines = output.split('\n');
        for (const line of lines) {
            const match = line.match(/^(.+):(\d+):(\d+):\s+(error|warning):\s+(.*)$/);
            if (!match) {
                continue;
            }

            const [, file, lineStr, , severity, message] = match;
            const lineNum = parseInt(lineStr, 10);

            this.addDiagnostic(
                diagnosticsMap,
                workspaceFolder,
                file,
                lineNum,
                message,
                'LEGACY',
                severity === 'error' ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning
            );
        }
    }

    /**
     * Clear all diagnostics
     */
    public clear(): void {
        this.diagnosticCollection.clear();
    }

    /**
     * Dispose resources
     */
    public dispose(): void {
        this.diagnosticCollection.dispose();
        this.outputChannel.dispose();
    }
}
