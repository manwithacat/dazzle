import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

/**
 * Claude Extension Integration for DAZZLE
 *
 * Detects Claude's VS Code extension and provides seamless SPEC → App workflow.
 *
 * Safe integration patterns:
 * 1. Check if Claude extension is installed
 * 2. Detect SPEC.md presence
 * 3. Show helpful notifications/actions
 * 4. Copy prompts to clipboard (user pastes)
 * 5. Use VS Code Chat API (if available)
 */

export interface ClaudeIntegrationOptions {
    autoDetect: boolean;
    showNotifications: boolean;
    preferClaudeForGeneration: boolean;
}

/**
 * Known Claude extension IDs (check marketplace for actual ID)
 */
const CLAUDE_EXTENSION_IDS = [
    'anthropic.claude',
    'anthropic.claude-vscode',
    'anthropic.claude-code',
    'saoudrizwan.claude-dev',  // Claude Dev (community)
];

/**
 * Check if Claude extension is installed
 */
export function isClaudeInstalled(): { installed: boolean; extensionId?: string } {
    for (const id of CLAUDE_EXTENSION_IDS) {
        const extension = vscode.extensions.getExtension(id);
        if (extension) {
            return { installed: true, extensionId: id };
        }
    }
    return { installed: false };
}

/**
 * Check if workspace has SPEC.md
 */
export function hasSpecFile(workspaceRoot: string): { exists: boolean; path?: string } {
    const specPatterns = ['SPEC.md', 'spec.md', 'SPECIFICATION.md', 'specification.md'];

    for (const pattern of specPatterns) {
        const specPath = path.join(workspaceRoot, pattern);
        if (fs.existsSync(specPath)) {
            return { exists: true, path: specPath };
        }
    }

    return { exists: false };
}

/**
 * Check if DSL directory is empty (or has only template)
 */
export function isDSLEmpty(workspaceRoot: string): boolean {
    const dslDir = path.join(workspaceRoot, 'dsl');

    if (!fs.existsSync(dslDir)) {
        return true;
    }

    const files = fs.readdirSync(dslDir);

    // Consider empty if no files or only template file
    if (files.length === 0) {
        return true;
    }

    // If only one file and it's the template
    if (files.length === 1 && files[0] === 'app.dsl') {
        const content = fs.readFileSync(path.join(dslDir, 'app.dsl'), 'utf-8');
        // Check if it's just the template (contains only comments and module declaration)
        const nonCommentLines = content
            .split('\n')
            .filter(line => line.trim() && !line.trim().startsWith('#'))
            .filter(line => !line.includes('module') && !line.includes('app'))
            .length;

        return nonCommentLines === 0;
    }

    return false;
}

/**
 * Generate prompt for Claude to transform SPEC → App
 */
export function generateClaudePrompt(specPath: string): string {
    return `I have a SPEC.md file with my application requirements in this DAZZLE project.

Please help me transform this specification into a working application by:

1. Reading the SPEC.md file to understand the requirements
2. Using DAZZLE's LLM integration to generate DSL:
   \`\`\`bash
   dazzle analyze-spec SPEC.md --no-interactive --generate-dsl
   \`\`\`
3. Validating the generated DSL:
   \`\`\`bash
   dazzle validate
   \`\`\`
4. Building the application:
   \`\`\`bash
   dazzle build --stack micro
   \`\`\`
5. Showing me how to run the generated application

Please proceed with these steps automatically and report any issues you encounter.`;
}

/**
 * Show notification when SPEC.md is detected without DSL
 */
export async function showSpecDetectedNotification(
    context: vscode.ExtensionContext,
    specPath: string
): Promise<void> {
    const claudeStatus = isClaudeInstalled();

    if (claudeStatus.installed) {
        // Claude is installed - offer to send prompt
        const action = await vscode.window.showInformationMessage(
            '💡 SPEC.md detected! Generate DAZZLE app with Claude?',
            'Copy Prompt to Clipboard',
            'Open Claude Chat',
            'Not Now',
            'Don\'t Show Again'
        );

        switch (action) {
            case 'Copy Prompt to Clipboard':
                await copyPromptToClipboard(specPath);
                vscode.window.showInformationMessage(
                    '✓ Prompt copied! Paste in Claude chat to generate your app.'
                );
                break;

            case 'Open Claude Chat':
                await openClaudeChat(context, specPath);
                break;

            case 'Don\'t Show Again':
                await context.globalState.update('dazzle.spec.dontShowNotification', true);
                break;
        }
    } else {
        // Claude not installed - offer alternatives
        const action = await vscode.window.showInformationMessage(
            '💡 SPEC.md detected! Generate DSL from specification?',
            'Run DAZZLE Analyze',
            'Install Claude Extension',
            'Not Now'
        );

        switch (action) {
            case 'Run DAZZLE Analyze':
                vscode.commands.executeCommand('dazzle.analyzeSpec');
                break;

            case 'Install Claude Extension':
                vscode.env.openExternal(vscode.Uri.parse(
                    'https://marketplace.visualstudio.com/items?itemName=anthropic.claude'
                ));
                break;
        }
    }
}

/**
 * Copy Claude prompt to clipboard
 */
async function copyPromptToClipboard(specPath: string): Promise<void> {
    const prompt = generateClaudePrompt(specPath);
    await vscode.env.clipboard.writeText(prompt);
}

/**
 * Open Claude chat (if extension provides API)
 */
async function openClaudeChat(context: vscode.ExtensionContext, specPath: string): Promise<void> {
    const claudeStatus = isClaudeInstalled();

    if (!claudeStatus.installed || !claudeStatus.extensionId) {
        vscode.window.showErrorMessage('Claude extension not found.');
        return;
    }

    // Try different approaches to open Claude chat

    // Approach 1: Check if Claude exposes a chat command
    const chatCommands = [
        'claude.openChat',
        'claude.newChat',
        'anthropic.openChat',
        'claude-dev.openChat'
    ];

    let chatOpened = false;
    for (const cmd of chatCommands) {
        try {
            const commands = await vscode.commands.getCommands();
            if (commands.includes(cmd)) {
                await vscode.commands.executeCommand(cmd);
                chatOpened = true;

                // Copy prompt to clipboard for user to paste
                await copyPromptToClipboard(specPath);
                vscode.window.showInformationMessage(
                    '✓ Claude chat opened! Prompt copied to clipboard - just paste to start.'
                );
                break;
            }
        } catch (error) {
            // Command doesn't exist or failed
            continue;
        }
    }

    // Approach 2: If no specific command, try VS Code's built-in chat API (if available)
    if (!chatOpened) {
        try {
            // VS Code 1.85+ has built-in chat API
            // @ts-ignore - May not be available in older versions
            if (vscode.chat) {
                await copyPromptToClipboard(specPath);
                vscode.window.showInformationMessage(
                    '✓ Open Claude chat panel and paste the prompt (copied to clipboard).'
                );
                return;
            }
        } catch {
            // Fall through
        }
    }

    // Approach 3: Fallback - copy to clipboard and show instructions
    if (!chatOpened) {
        await copyPromptToClipboard(specPath);
        vscode.window.showInformationMessage(
            '✓ Prompt copied to clipboard! Open Claude chat and paste to generate your app.',
            'Open Command Palette'
        ).then(action => {
            if (action === 'Open Command Palette') {
                vscode.commands.executeCommand('workbench.action.quickOpen', '>claude');
            }
        });
    }
}

/**
 * Register status bar item for SPEC → App workflow
 */
export function createSpecStatusBarItem(context: vscode.ExtensionContext): vscode.StatusBarItem {
    const statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Right,
        100
    );

    statusBarItem.text = '$(sparkle) Generate App';
    statusBarItem.tooltip = 'Generate DAZZLE app from SPEC.md';
    statusBarItem.command = 'dazzle.generateFromSpec';

    context.subscriptions.push(statusBarItem);

    return statusBarItem;
}

/**
 * Update status bar based on workspace state
 */
export function updateSpecStatusBar(
    statusBarItem: vscode.StatusBarItem,
    workspaceRoot: string | undefined
): void {
    if (!workspaceRoot) {
        statusBarItem.hide();
        return;
    }

    const specFile = hasSpecFile(workspaceRoot);
    const dslEmpty = isDSLEmpty(workspaceRoot);

    if (specFile.exists && dslEmpty) {
        // Show "Generate from SPEC" indicator
        const claudeStatus = isClaudeInstalled();

        if (claudeStatus.installed) {
            statusBarItem.text = '$(sparkle) Ask Claude to Generate App';
            statusBarItem.tooltip = 'Click to generate DAZZLE app from SPEC.md using Claude';
        } else {
            statusBarItem.text = '$(beaker) Generate DSL from SPEC';
            statusBarItem.tooltip = 'Click to analyze SPEC.md and generate DSL';
        }

        statusBarItem.show();
    } else {
        statusBarItem.hide();
    }
}

/**
 * Register the "Generate from SPEC" command
 */
export function registerGenerateFromSpecCommand(context: vscode.ExtensionContext): void {
    const command = vscode.commands.registerCommand('dazzle.generateFromSpec', async () => {
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

        if (!workspaceRoot) {
            vscode.window.showErrorMessage('No workspace folder opened.');
            return;
        }

        const specFile = hasSpecFile(workspaceRoot);

        if (!specFile.exists) {
            vscode.window.showErrorMessage('No SPEC.md file found in workspace.');
            return;
        }

        await showSpecDetectedNotification(context, specFile.path!);
    });

    context.subscriptions.push(command);
}

/**
 * Auto-detect SPEC.md and show notification on workspace open
 */
export async function autoDetectSpec(context: vscode.ExtensionContext): Promise<void> {
    // Check if user has disabled notifications
    const dontShow = context.globalState.get('dazzle.spec.dontShowNotification', false);
    if (dontShow) {
        return;
    }

    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

    if (!workspaceRoot) {
        return;
    }

    const specFile = hasSpecFile(workspaceRoot);
    const dslEmpty = isDSLEmpty(workspaceRoot);

    // Only show if SPEC exists and DSL is empty
    if (specFile.exists && dslEmpty) {
        // Wait a bit to let workspace settle
        setTimeout(() => {
            showSpecDetectedNotification(context, specFile.path!);
        }, 2000);
    }
}

/**
 * Watch for SPEC.md creation
 */
export function watchForSpecChanges(
    context: vscode.ExtensionContext,
    statusBarItem: vscode.StatusBarItem
): void {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

    if (!workspaceRoot) {
        return;
    }

    // Watch for file changes
    const watcher = vscode.workspace.createFileSystemWatcher(
        new vscode.RelativePattern(workspaceRoot, '**/{SPEC,spec}.md')
    );

    watcher.onDidCreate(() => {
        updateSpecStatusBar(statusBarItem, workspaceRoot);
        autoDetectSpec(context);
    });

    watcher.onDidChange(() => {
        updateSpecStatusBar(statusBarItem, workspaceRoot);
    });

    watcher.onDidDelete(() => {
        updateSpecStatusBar(statusBarItem, workspaceRoot);
    });

    context.subscriptions.push(watcher);
}
