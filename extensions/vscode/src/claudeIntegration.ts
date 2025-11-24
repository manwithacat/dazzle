import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Claude Integration for DAZZLE
 *
 * Simple integration that detects Claude Code and provides prompt templates
 * for common DAZZLE workflows. Uses clipboard-based handoff pattern.
 */

/**
 * Known Claude extension IDs
 */
const CLAUDE_EXTENSION_IDS = [
    'anthropic.claude',
    'anthropic.claude-vscode',
    'anthropic.claude-code',
    'saoudrizwan.claude-dev',
];

/**
 * Pre-crafted prompts for common workflows
 */
const PROMPTS = {
    analyzeSpec: (specPath: string) => `I have a SPEC.md file in this DAZZLE project.

Please help me transform this specification into a working application:

1. Read ${specPath}
2. Run: dazzle analyze-spec ${specPath} --no-interactive --generate-dsl
3. Run: dazzle validate
4. Run: dazzle build --stack micro
5. Show me how to run the generated application

Proceed automatically and report any issues you encounter.`,

    validateAndFix: `Please validate this DAZZLE project and fix any errors:

1. Run: dazzle validate
2. Fix any validation errors you find
3. Run: dazzle validate again to confirm
4. Summarize what was fixed`,

    build: (stack: string = 'micro') => `Please build this DAZZLE project:

1. Run: dazzle validate
2. Run: dazzle build --stack ${stack}
3. Show me the generated files
4. Explain how to run the application`,

    init: `Please help me initialize a new DAZZLE project:

1. Run: dazzle init
2. Show me the project structure
3. Guide me on next steps to define my application`
};

/**
 * Check if Claude extension is installed
 */
export function isClaudeInstalled(): boolean {
    for (const id of CLAUDE_EXTENSION_IDS) {
        if (vscode.extensions.getExtension(id)) {
            return true;
        }
    }
    return false;
}

/**
 * Check if workspace has SPEC.md
 */
export function hasSpecFile(workspaceRoot: string): string | null {
    const specPatterns = ['SPEC.md', 'spec.md', 'SPECIFICATION.md'];
    for (const pattern of specPatterns) {
        const specPath = path.join(workspaceRoot, pattern);
        if (fs.existsSync(specPath)) {
            return specPath;
        }
    }
    return null;
}

/**
 * Copy prompt to clipboard and notify user
 */
async function copyPromptAndNotify(prompt: string, action: string): Promise<void> {
    await vscode.env.clipboard.writeText(prompt);
    vscode.window.showInformationMessage(
        `✓ ${action} prompt copied to clipboard! Paste in Claude chat to proceed.`,
        'Open Command Palette'
    ).then(choice => {
        if (choice === 'Open Command Palette') {
            vscode.commands.executeCommand('workbench.action.quickOpen', '>');
        }
    });
}

/**
 * Register all Claude integration commands
 */
export function registerClaudeCommands(context: vscode.ExtensionContext): void {
    // Command: Ask Claude to analyze SPEC
    context.subscriptions.push(
        vscode.commands.registerCommand('dazzle.askClaudeToAnalyze', async () => {
            const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
            if (!workspaceRoot) {
                vscode.window.showErrorMessage('No workspace folder opened.');
                return;
            }

            const specPath = hasSpecFile(workspaceRoot);
            if (!specPath) {
                vscode.window.showErrorMessage('No SPEC.md file found in workspace.');
                return;
            }

            const prompt = PROMPTS.analyzeSpec(path.basename(specPath));
            await copyPromptAndNotify(prompt, 'Analyze SPEC');
        })
    );

    // Command: Ask Claude to validate and fix
    context.subscriptions.push(
        vscode.commands.registerCommand('dazzle.askClaudeToFix', async () => {
            await copyPromptAndNotify(PROMPTS.validateAndFix, 'Validate & Fix');
        })
    );

    // Command: Ask Claude to build
    context.subscriptions.push(
        vscode.commands.registerCommand('dazzle.askClaudeToBuild', async () => {
            const stack = await vscode.window.showQuickPick(
                ['micro', 'django_api', 'express_micro', 'openapi', 'docker', 'terraform'],
                { placeHolder: 'Select stack to build' }
            );
            if (stack) {
                const prompt = PROMPTS.build(stack);
                await copyPromptAndNotify(prompt, `Build (${stack})`);
            }
        })
    );

    // Command: Ask Claude to initialize project
    context.subscriptions.push(
        vscode.commands.registerCommand('dazzle.askClaudeToInit', async () => {
            await copyPromptAndNotify(PROMPTS.init, 'Initialize Project');
        })
    );
}

/**
 * Create status bar item for SPEC → App workflow
 */
export function createSpecStatusBar(context: vscode.ExtensionContext): vscode.StatusBarItem | null {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceRoot) {
        return null;
    }

    const specPath = hasSpecFile(workspaceRoot);
    if (!specPath) {
        return null;
    }

    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );

    const claudeInstalled = isClaudeInstalled();
    if (claudeInstalled) {
        statusBarItem.text = '$(sparkle) Ask Claude';
        statusBarItem.tooltip = 'Ask Claude to generate DAZZLE app from SPEC.md';
    } else {
        statusBarItem.text = '$(beaker) Generate from SPEC';
        statusBarItem.tooltip = 'Generate DAZZLE app from SPEC.md';
    }

    statusBarItem.command = 'dazzle.askClaudeToAnalyze';
    statusBarItem.show();

    context.subscriptions.push(statusBarItem);
    return statusBarItem;
}

/**
 * Auto-detect SPEC.md and show helpful notification (once)
 */
export function autoDetectSpec(context: vscode.ExtensionContext): void {
    // Check if we've already shown this notification
    const hasShown = context.globalState.get('dazzle.spec.notificationShown', false);
    if (hasShown) {
        return;
    }

    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceRoot) {
        return;
    }

    const specPath = hasSpecFile(workspaceRoot);
    if (!specPath) {
        return;
    }

    // Check if DSL directory exists and has files
    const dslDir = path.join(workspaceRoot, 'dsl');
    const hasDSL = fs.existsSync(dslDir) && fs.readdirSync(dslDir).length > 0;

    if (hasDSL) {
        // Already has DSL, don't bother user
        return;
    }

    // Show notification
    const claudeInstalled = isClaudeInstalled();
    const message = claudeInstalled
        ? '💡 SPEC.md detected! Ask Claude to generate your DAZZLE app?'
        : '💡 SPEC.md detected! Would you like to generate DSL?';

    const action = claudeInstalled ? 'Ask Claude' : 'Generate DSL';

    vscode.window.showInformationMessage(
        message,
        action,
        'Not Now',
        "Don't Show Again"
    ).then(choice => {
        if (choice === action) {
            vscode.commands.executeCommand('dazzle.askClaudeToAnalyze');
        } else if (choice === "Don't Show Again") {
            context.globalState.update('dazzle.spec.notificationShown', true);
        }
    });

    // Mark as shown (even if they clicked "Not Now")
    context.globalState.update('dazzle.spec.notificationShown', true);
}
