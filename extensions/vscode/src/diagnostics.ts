import * as vscode from 'vscode';
import * as child_process from 'child_process';
import * as path from 'path';

/**
 * Diagnostics Provider for DAZZLE DSL files
 *
 * Runs `dazzle validate --format vscode` and parses output to create diagnostics
 */

export class DazzleDiagnostics {
    private diagnosticCollection: vscode.DiagnosticCollection;
    private outputChannel: vscode.OutputChannel;

    constructor() {
        this.diagnosticCollection = vscode.languages.createDiagnosticCollection('dazzle');
        this.outputChannel = vscode.window.createOutputChannel('DAZZLE');
        // Show the output channel to ensure it's visible
        this.outputChannel.show(true);
        this.outputChannel.appendLine('DAZZLE extension initialized');
    }

    /**
     * Run validation and update diagnostics
     */
    public async validateWorkspace(workspaceFolder: vscode.WorkspaceFolder): Promise<void> {
        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');
        const manifestName = config.get<string>('manifest', 'dazzle.toml');

        this.outputChannel.appendLine(`Running validation in ${workspaceFolder.uri.fsPath}...`);

        try {
            const result = await this.runValidation(workspaceFolder.uri.fsPath, cliPath, manifestName);
            this.processValidationOutput(result, workspaceFolder);
        } catch (error) {
            this.outputChannel.appendLine(`Validation error: ${error}`);
            vscode.window.showErrorMessage(`DAZZLE validation failed: ${error}`);
        }
    }

    /**
     * Run dazzle validate command
     */
    private runValidation(cwd: string, cliPath: string, manifestName: string): Promise<string> {
        return new Promise((resolve, reject) => {
            const args = ['validate', '--format', 'vscode', '--manifest', manifestName];

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
                // Combine stdout and stderr (validation output goes to stderr)
                const output = stdout + stderr;
                this.outputChannel.appendLine(`Validation completed with code ${code}`);
                this.outputChannel.appendLine(output);
                resolve(output);
            });

            childProcess.on('error', (error: Error) => {
                reject(new Error(`Failed to run DAZZLE CLI: ${error.message}`));
            });
        });
    }

    /**
     * Parse validation output and create VS Code diagnostics
     */
    private processValidationOutput(output: string, workspaceFolder: vscode.WorkspaceFolder): void {
        // Clear existing diagnostics
        this.diagnosticCollection.clear();

        const diagnosticsMap = new Map<string, vscode.Diagnostic[]>();

        // Parse each line: file:line:col: severity: message
        const lines = output.split('\n');
        for (const line of lines) {
            const match = line.match(/^(.+):(\d+):(\d+):\s+(error|warning):\s+(.*)$/);
            if (!match) {
                continue;
            }

            const [, file, lineStr, colStr, severity, message] = match;
            const lineNum = parseInt(lineStr, 10) - 1; // VS Code uses 0-based line numbers
            const colNum = parseInt(colStr, 10) - 1;   // VS Code uses 0-based column numbers

            // Create VS Code diagnostic
            const range = new vscode.Range(
                new vscode.Position(lineNum, colNum),
                new vscode.Position(lineNum, colNum + 1)
            );

            const diagnostic = new vscode.Diagnostic(
                range,
                message,
                severity === 'error' ? vscode.DiagnosticSeverity.Error : vscode.DiagnosticSeverity.Warning
            );

            diagnostic.source = 'DAZZLE';

            // Resolve file path relative to workspace
            const filePath = path.isAbsolute(file)
                ? file
                : path.join(workspaceFolder.uri.fsPath, file);

            const fileUri = vscode.Uri.file(filePath);

            // Add to diagnostics map
            if (!diagnosticsMap.has(filePath)) {
                diagnosticsMap.set(filePath, []);
            }
            diagnosticsMap.get(filePath)!.push(diagnostic);
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
            this.outputChannel.appendLine('No issues found ✓');
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
