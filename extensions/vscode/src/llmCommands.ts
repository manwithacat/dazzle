import * as vscode from 'vscode';
import * as child_process from 'child_process';
import * as path from 'path';
import { AnalysisPanelProvider } from './ui/analysisPanel';

/**
 * LLM-assisted spec analysis commands for DAZZLE
 *
 * Implements spec analysis, Q&A workflow, and DSL generation.
 */

// Simple type that matches the JSON from CLI
type SpecAnalysis = any;

interface AnalysisResult {
    success: boolean;
    analysis?: SpecAnalysis;
    error?: string;
}

// Global panel provider instance
let analysisPanelProvider: AnalysisPanelProvider | undefined;

export function registerLLMCommands(context: vscode.ExtensionContext): void {
    // Initialize panel provider
    analysisPanelProvider = new AnalysisPanelProvider(context);

    // Register analyze-spec command
    const analyzeSpecCmd = vscode.commands.registerCommand('dazzle.analyzeSpec', async () => {
        await analyzeSpecCommand(context);
    });

    context.subscriptions.push(analyzeSpecCmd);
}

/**
 * Main command handler for spec analysis
 */
async function analyzeSpecCommand(context: vscode.ExtensionContext): Promise<void> {
    // Check if active editor has a markdown file
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
        vscode.window.showErrorMessage('Please open a specification file (e.g., SPEC.md) to analyze.');
        return;
    }

    const document = editor.document;
    const fileName = path.basename(document.fileName);

    // Check if it's a markdown or text file
    if (!fileName.toLowerCase().endsWith('.md') && !fileName.toLowerCase().endsWith('.txt')) {
        const proceed = await vscode.window.showWarningMessage(
            `File "${fileName}" doesn't appear to be a specification file. Analyze anyway?`,
            'Yes', 'No'
        );
        if (proceed !== 'Yes') {
            return;
        }
    }

    // Check for API key
    const apiKeyConfigured = await checkAPIKeyConfigured();
    if (!apiKeyConfigured) {
        const setup = await vscode.window.showErrorMessage(
            'No LLM API key configured. Please set ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.',
            'Configure Settings'
        );
        if (setup === 'Configure Settings') {
            vscode.commands.executeCommand('workbench.action.openSettings', 'dazzle.llm');
        }
        return;
    }

    // Estimate cost and confirm
    const specContent = document.getText();
    const specSizeKB = Buffer.byteLength(specContent) / 1024;
    const estimatedCost = estimateCost(specSizeKB);

    if (estimatedCost > 0.50) {
        const proceed = await vscode.window.showWarningMessage(
            `Analyzing this specification will cost approximately $${estimatedCost.toFixed(2)}. Continue?`,
            'Yes', 'No'
        );
        if (proceed !== 'Yes') {
            return;
        }
    }

    // Run analysis
    const analysisResult = await vscode.window.withProgress(
        {
            location: vscode.ProgressLocation.Notification,
            title: 'Analyzing specification with LLM...',
            cancellable: false
        },
        async (progress) => {
            progress.report({ message: 'Extracting state machines and CRUD operations...' });
            return await runSpecAnalysis(document.fileName, specContent);
        }
    );

    if (!analysisResult.success || !analysisResult.analysis) {
        vscode.window.showErrorMessage(`Specification analysis failed: ${analysisResult.error || 'Unknown error'}`);
        return;
    }

    // Show comprehensive analysis dashboard
    if (analysisPanelProvider) {
        analysisPanelProvider.show(analysisResult.analysis);
    }

    // Show brief summary notification
    await showAnalysisResults(analysisResult.analysis);

    // Ask if user wants to proceed with Q&A
    const proceedWithQA = await vscode.window.showInformationMessage(
        `Analysis complete! Found ${analysisResult.analysis.clarifying_questions.length} categories of questions. Proceed with Q&A?`,
        'Yes', 'Skip Q&A', 'Cancel'
    );

    if (proceedWithQA === 'Yes') {
        // Run interactive Q&A
        const answers = await runInteractiveQA(analysisResult.analysis);

        if (answers) {
            // Generate DSL
            const generateDSL = await vscode.window.showInformationMessage(
                'All questions answered! Generate DSL now?',
                'Yes', 'No'
            );

            if (generateDSL === 'Yes') {
                await generateDSLFromAnalysis(analysisResult.analysis, answers, document.fileName);
            }
        }
    } else if (proceedWithQA === 'Skip Q&A') {
        // Offer to generate DSL without Q&A
        const generateDSL = await vscode.window.showInformationMessage(
            'Generate DSL without answering questions?',
            'Yes', 'No'
        );

        if (generateDSL === 'Yes') {
            await generateDSLFromAnalysis(analysisResult.analysis, new Map(), document.fileName);
        }
    }
}

/**
 * Check if API key is configured
 */
async function checkAPIKeyConfigured(): Promise<boolean> {
    // Check environment variables
    return process.env.ANTHROPIC_API_KEY !== undefined || process.env.OPENAI_API_KEY !== undefined;
}

/**
 * Estimate cost of analysis
 */
function estimateCost(specSizeKB: number): number {
    // Rough estimation: 1KB ≈ 750 tokens
    const inputTokens = specSizeKB * 750 + 500; // + system prompt
    const outputTokens = 8000; // Estimated output size

    // Claude Sonnet pricing
    const inputCost = inputTokens * (3.00 / 1_000_000);
    const outputCost = outputTokens * (15.00 / 1_000_000);

    return inputCost + outputCost;
}

/**
 * Run spec analysis via DAZZLE CLI
 */
async function runSpecAnalysis(specPath: string, specContent: string): Promise<AnalysisResult> {
    return new Promise((resolve) => {
        const config = vscode.workspace.getConfiguration('dazzle');
        const cliPath = config.get<string>('cliPath', 'dazzle');

        // Call: dazzle analyze-spec <path> --output-json
        const child = child_process.spawn(
            cliPath,
            ['analyze-spec', specPath, '--output-json'],
            {
                cwd: path.dirname(specPath),
                env: process.env
            }
        );

        let stdout = '';
        let stderr = '';

        child.stdout.on('data', (data) => {
            stdout += data.toString();
        });

        child.stderr.on('data', (data) => {
            stderr += data.toString();
        });

        child.on('close', (code) => {
            if (code === 0) {
                try {
                    const analysis: SpecAnalysis = JSON.parse(stdout);
                    resolve({ success: true, analysis });
                } catch (e) {
                    resolve({ success: false, error: `Failed to parse analysis JSON: ${e}` });
                }
            } else {
                resolve({ success: false, error: stderr || `Exit code: ${code}` });
            }
        });

        child.on('error', (error) => {
            resolve({ success: false, error: error.message });
        });
    });
}

/**
 * Show analysis results summary
 */
async function showAnalysisResults(analysis: any): Promise<void> {
    const stateMachineCount = analysis.state_machines?.length || 0;
    const entityCount = analysis.crud_analysis?.length || 0;
    const questionCount = (analysis.clarifying_questions || []).reduce(
        (sum: number, cat: any) => sum + (cat.questions?.length || 0),
        0
    );

    vscode.window.showInformationMessage(
        `Spec analysis complete! ${stateMachineCount} state machines, ${entityCount} entities, ${questionCount} questions.`
    );
}

/**
 * Run interactive Q&A workflow
 */
async function runInteractiveQA(analysis: any): Promise<Map<string, string> | null> {
    const answers = new Map<string, string>();

    for (const category of (analysis.clarifying_questions || [])) {
        // Show category header
        const proceed = await vscode.window.showInformationMessage(
            `${category.category} (Priority: ${category.priority})`,
            'Continue', 'Skip Category'
        );

        if (proceed !== 'Continue') {
            continue;
        }

        for (const question of category.questions) {
            // Create QuickPick items
            const items = question.options.map(opt => ({
                label: opt,
                detail: question.context,
                description: question.impacts
            }));

            const selected = await vscode.window.showQuickPick(items, {
                placeHolder: question.q,
                ignoreFocusOut: true,
                title: `${category.category} - Question ${category.questions.indexOf(question) + 1}/${category.questions.length}`
            });

            if (!selected) {
                // User cancelled
                const cancel = await vscode.window.showWarningMessage(
                    'Q&A cancelled. Discard all answers?',
                    'Yes', 'No'
                );
                if (cancel === 'Yes') {
                    return null;
                }
                // If No, continue with what we have
                break;
            }

            answers.set(question.q, selected.label);
        }
    }

    return answers;
}

/**
 * Generate DSL from analysis and answers
 */
async function generateDSLFromAnalysis(
    analysis: any,
    answers: Map<string, string>,
    specPath: string
): Promise<void> {
    // Call DAZZLE CLI to generate DSL
    const config = vscode.workspace.getConfiguration('dazzle');
    const cliPath = config.get<string>('cliPath', 'dazzle');

    const terminal = vscode.window.createTerminal({
        name: 'DAZZLE DSL Generation',
        cwd: path.dirname(specPath)
    });

    terminal.show();

    // TODO: Implement DSL generation command
    terminal.sendText(`${cliPath} generate-dsl ${specPath} --from-analysis`);

    vscode.window.showInformationMessage('DSL generation started. Check terminal for output.');
}
