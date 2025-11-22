import * as vscode from 'vscode';
import * as path from 'path';

/**
 * Analysis Dashboard Panel
 *
 * Displays comprehensive visualization of spec analysis results including:
 * - Interactive state machine diagrams
 * - CRUD coverage matrix
 * - Business rules visualization
 * - Coverage metrics dashboard
 * - Question priority breakdown
 */

interface AnalysisData {
    state_machines: StateMachine[];
    crud_analysis: CRUDAnalysis[];
    business_rules: BusinessRule[];
    clarifying_questions: QuestionCategory[];
}

interface StateMachine {
    entity: string;
    field: string;
    states: string[];
    transitions_found: Transition[];
    transitions_implied_but_missing: ImpliedTransition[];
}

interface Transition {
    from: string;
    to: string;
    trigger: string;
    who_can_trigger?: string;
    side_effects?: string[];
    conditions?: string[];
}

interface ImpliedTransition {
    from: string;
    to: string;
    reason: string;
    question: string;
}

interface CRUDAnalysis {
    entity: string;
    operations_mentioned: { [key: string]: any };
    missing_operations: string[];
}

interface BusinessRule {
    type: string;
    entity: string;
    field?: string;
    rule: string;
}

interface QuestionCategory {
    category: string;
    priority: string;
    questions: Question[];
}

interface Question {
    q: string;
    context: string;
    options: string[];
    impacts: string;
}

export class AnalysisPanelProvider {
    private panel: vscode.WebviewPanel | undefined;
    private context: vscode.ExtensionContext;

    constructor(context: vscode.ExtensionContext) {
        this.context = context;
    }

    public show(analysis: AnalysisData) {
        if (this.panel) {
            this.panel.reveal(vscode.ViewColumn.Two);
        } else {
            this.panel = vscode.window.createWebviewPanel(
                'dazzleAnalysis',
                'DAZZLE Spec Analysis',
                vscode.ViewColumn.Two,
                {
                    enableScripts: true,
                    retainContextWhenHidden: true,
                    localResourceRoots: [
                        vscode.Uri.file(path.join(this.context.extensionPath, 'media'))
                    ]
                }
            );

            this.panel.onDidDispose(() => {
                this.panel = undefined;
            });
        }

        this.panel.webview.html = this.getWebviewContent(analysis);
    }

    private getWebviewContent(analysis: AnalysisData): string {
        const stateMachines = this.generateStateMachineDiagrams(analysis.state_machines);
        const crudMatrix = this.generateCRUDMatrix(analysis.crud_analysis);
        const businessRulesViz = this.generateBusinessRulesVisualization(analysis.business_rules);
        const coverageMetrics = this.generateCoverageMetrics(analysis);
        const questionsPriority = this.generateQuestionsPriorityChart(analysis.clarifying_questions);

        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DAZZLE Spec Analysis</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <style>
        :root {
            --bg-primary: var(--vscode-editor-background);
            --bg-secondary: var(--vscode-editorWidget-background);
            --fg-primary: var(--vscode-editor-foreground);
            --fg-secondary: var(--vscode-descriptionForeground);
            --accent: var(--vscode-focusBorder);
            --success: #4caf50;
            --warning: #ff9800;
            --danger: #f44336;
            --info: #2196f3;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: var(--vscode-font-family);
            color: var(--fg-primary);
            background: var(--bg-primary);
            padding: 20px;
            line-height: 1.6;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        h1 {
            font-size: 2em;
            margin-bottom: 10px;
            color: var(--accent);
        }

        h2 {
            font-size: 1.5em;
            margin: 30px 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid var(--accent);
        }

        h3 {
            font-size: 1.2em;
            margin: 20px 0 10px 0;
            color: var(--fg-primary);
        }

        .summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }

        .metric-card {
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: 8px;
            border-left: 4px solid var(--accent);
        }

        .metric-card h3 {
            margin: 0 0 10px 0;
            font-size: 0.9em;
            text-transform: uppercase;
            color: var(--fg-secondary);
        }

        .metric-value {
            font-size: 2.5em;
            font-weight: bold;
            color: var(--fg-primary);
        }

        .metric-label {
            font-size: 0.9em;
            color: var(--fg-secondary);
            margin-top: 5px;
        }

        .section {
            background: var(--bg-secondary);
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .state-machine {
            margin-bottom: 30px;
        }

        .mermaid {
            background: white;
            padding: 20px;
            border-radius: 5px;
            margin: 10px 0;
        }

        .crud-matrix {
            overflow-x: auto;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }

        th, td {
            padding: 12px;
            text-align: left;
            border: 1px solid var(--vscode-panel-border);
        }

        th {
            background: var(--bg-primary);
            font-weight: bold;
            position: sticky;
            top: 0;
        }

        .status-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: bold;
        }

        .status-found {
            background: var(--success);
            color: white;
        }

        .status-missing {
            background: var(--danger);
            color: white;
        }

        .status-partial {
            background: var(--warning);
            color: white;
        }

        .rule-list {
            list-style: none;
        }

        .rule-item {
            padding: 10px;
            margin: 5px 0;
            background: var(--bg-primary);
            border-left: 3px solid var(--info);
            border-radius: 4px;
        }

        .rule-type {
            display: inline-block;
            padding: 2px 8px;
            background: var(--accent);
            color: white;
            border-radius: 3px;
            font-size: 0.8em;
            margin-right: 10px;
        }

        .chart-container {
            position: relative;
            height: 300px;
            margin: 20px 0;
        }

        .legend {
            display: flex;
            gap: 20px;
            margin: 15px 0;
            flex-wrap: wrap;
        }

        .legend-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .legend-color {
            width: 20px;
            height: 20px;
            border-radius: 3px;
        }

        .transition-list {
            margin: 15px 0;
        }

        .transition-item {
            padding: 10px;
            margin: 5px 0;
            background: var(--bg-primary);
            border-radius: 4px;
            border-left: 3px solid var(--success);
        }

        .transition-missing {
            border-left-color: var(--warning);
        }

        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 2px solid var(--vscode-panel-border);
        }

        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            background: transparent;
            color: var(--fg-secondary);
            font-size: 1em;
            transition: all 0.3s;
        }

        .tab:hover {
            color: var(--fg-primary);
        }

        .tab.active {
            color: var(--accent);
            border-bottom: 2px solid var(--accent);
            margin-bottom: -2px;
        }

        .tab-content {
            display: none;
        }

        .tab-content.active {
            display: block;
        }

        .progress-bar {
            width: 100%;
            height: 24px;
            background: var(--bg-primary);
            border-radius: 12px;
            overflow: hidden;
            margin: 10px 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--success), var(--info));
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            font-size: 0.85em;
            transition: width 0.5s ease;
        }

        .export-buttons {
            display: flex;
            gap: 10px;
            margin: 20px 0;
        }

        button {
            padding: 10px 20px;
            background: var(--accent);
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 0.9em;
            transition: opacity 0.3s;
        }

        button:hover {
            opacity: 0.8;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Specification Analysis Dashboard</h1>
        <p style="color: var(--fg-secondary); margin-bottom: 30px;">
            Comprehensive analysis of your application specification
        </p>

        <!-- Summary Metrics -->
        ${coverageMetrics}

        <!-- Tabs -->
        <div class="tabs">
            <button class="tab active" onclick="showTab('state-machines')">State Machines</button>
            <button class="tab" onclick="showTab('crud')">CRUD Coverage</button>
            <button class="tab" onclick="showTab('rules')">Business Rules</button>
            <button class="tab" onclick="showTab('questions')">Questions</button>
        </div>

        <!-- State Machines Tab -->
        <div id="state-machines" class="tab-content active">
            <h2>🔄 State Machines</h2>
            ${stateMachines}
        </div>

        <!-- CRUD Coverage Tab -->
        <div id="crud" class="tab-content">
            <h2>📋 CRUD Coverage Matrix</h2>
            ${crudMatrix}
        </div>

        <!-- Business Rules Tab -->
        <div id="rules" class="tab-content">
            <h2>📏 Business Rules</h2>
            ${businessRulesViz}
        </div>

        <!-- Questions Tab -->
        <div id="questions" class="tab-content">
            <h2>❓ Clarifying Questions</h2>
            ${questionsPriority}
        </div>

        <!-- Export Section -->
        <div class="section">
            <h3>Export & Share</h3>
            <div class="export-buttons">
                <button onclick="exportPDF()">📄 Export as PDF</button>
                <button onclick="exportMarkdown()">📝 Export as Markdown</button>
                <button onclick="copyToClipboard()">📋 Copy Summary</button>
            </div>
        </div>
    </div>

    <script>
        // Initialize Mermaid
        mermaid.initialize({
            startOnLoad: true,
            theme: 'default',
            themeVariables: {
                primaryColor: '#4a90e2',
                primaryTextColor: '#fff',
                primaryBorderColor: '#2c3e50',
                lineColor: '#34495e',
                secondaryColor: '#95a5a6',
                tertiaryColor: '#ecf0f1'
            }
        });

        // Tab switching
        function showTab(tabName) {
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });

            // Show selected tab
            document.getElementById(tabName).classList.add('active');
            event.target.classList.add('active');
        }

        // Export functions (placeholder - would need actual implementation)
        function exportPDF() {
            alert('PDF export would open print dialog or generate PDF');
        }

        function exportMarkdown() {
            alert('Markdown export would generate downloadable .md file');
        }

        function copyToClipboard() {
            const summary = generateSummary();
            navigator.clipboard.writeText(summary);
            alert('Summary copied to clipboard!');
        }

        function generateSummary() {
            return 'Specification Analysis Summary (see dashboard for details)';
        }

        // Animate progress bars on load
        window.addEventListener('load', () => {
            document.querySelectorAll('.progress-fill').forEach(bar => {
                const width = bar.style.width;
                bar.style.width = '0%';
                setTimeout(() => {
                    bar.style.width = width;
                }, 100);
            });
        });
    </script>
</body>
</html>`;
    }

    private generateStateMachineDiagrams(stateMachines: StateMachine[]): string {
        if (!stateMachines || stateMachines.length === 0) {
            return '<p style="color: var(--fg-secondary);">No state machines detected in specification.</p>';
        }

        return stateMachines.map(sm => {
            // Generate Mermaid diagram
            let mermaid = 'stateDiagram-v2\n';

            // Add transitions
            for (const trans of sm.transitions_found) {
                mermaid += `    ${trans.from} --> ${trans.to}: ${trans.trigger}\n`;
            }

            // Add missing transitions (dashed)
            for (const missing of sm.transitions_implied_but_missing) {
                mermaid += `    ${missing.from} -.-> ${missing.to}: ⚠️ ${missing.reason}\n`;
            }

            // Generate transition details list
            const transitionsList = `
                <div class="transition-list">
                    <h4>Found Transitions:</h4>
                    ${sm.transitions_found.map(t => `
                        <div class="transition-item">
                            <strong>${t.from} → ${t.to}</strong>
                            <div>Trigger: ${t.trigger}</div>
                            ${t.who_can_trigger ? `<div>Who: ${t.who_can_trigger}</div>` : ''}
                            ${t.conditions && t.conditions.length > 0 ? `<div>Conditions: ${t.conditions.join(', ')}</div>` : ''}
                            ${t.side_effects && t.side_effects.length > 0 ? `<div>Side effects: ${t.side_effects.join(', ')}</div>` : ''}
                        </div>
                    `).join('')}

                    ${sm.transitions_implied_but_missing.length > 0 ? `
                        <h4 style="margin-top: 20px;">Missing Transitions:</h4>
                        ${sm.transitions_implied_but_missing.map(m => `
                            <div class="transition-item transition-missing">
                                <strong>⚠️ ${m.from} → ${m.to}</strong>
                                <div>Reason: ${m.reason}</div>
                                <div style="font-style: italic;">Question: ${m.question}</div>
                            </div>
                        `).join('')}
                    ` : ''}
                </div>
            `;

            return `
                <div class="section state-machine">
                    <h3>${sm.entity}.${sm.field}</h3>
                    <div style="color: var(--fg-secondary); margin-bottom: 15px;">
                        States: ${sm.states.join(', ')}
                    </div>
                    <div class="mermaid">
                        ${mermaid}
                    </div>
                    ${transitionsList}
                </div>
            `;
        }).join('');
    }

    private generateCRUDMatrix(crudAnalysis: CRUDAnalysis[]): string {
        if (!crudAnalysis || crudAnalysis.length === 0) {
            return '<p style="color: var(--fg-secondary);">No CRUD analysis available.</p>';
        }

        const operations = ['create', 'read', 'update', 'delete', 'list'];

        return `
            <div class="section crud-matrix">
                <table>
                    <thead>
                        <tr>
                            <th>Entity</th>
                            ${operations.map(op => `<th>${op.charAt(0).toUpperCase() + op.slice(1)}</th>`).join('')}
                            <th>Coverage</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${crudAnalysis.map(crud => {
                            const found = operations.filter(op =>
                                crud.operations_mentioned[op]?.found === true
                            ).length;
                            const coverage = (found / operations.length * 100).toFixed(0);

                            return `
                                <tr>
                                    <td><strong>${crud.entity}</strong></td>
                                    ${operations.map(op => {
                                        const opData = crud.operations_mentioned[op];
                                        const isFound = opData?.found === true;
                                        return `
                                            <td>
                                                <span class="status-badge ${isFound ? 'status-found' : 'status-missing'}">
                                                    ${isFound ? '✓' : '✗'}
                                                </span>
                                            </td>
                                        `;
                                    }).join('')}
                                    <td>
                                        <div class="progress-bar">
                                            <div class="progress-fill" style="width: ${coverage}%">
                                                ${coverage}%
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    private generateBusinessRulesVisualization(rules: BusinessRule[]): string {
        if (!rules || rules.length === 0) {
            return '<p style="color: var(--fg-secondary);">No business rules detected.</p>';
        }

        // Group by type
        const rulesByType: { [key: string]: BusinessRule[] } = {};
        rules.forEach(rule => {
            if (!rulesByType[rule.type]) {
                rulesByType[rule.type] = [];
            }
            rulesByType[rule.type].push(rule);
        });

        return Object.entries(rulesByType).map(([type, typeRules]) => `
            <div class="section">
                <h3>${type.replace('_', ' ').toUpperCase()} (${typeRules.length})</h3>
                <ul class="rule-list">
                    ${typeRules.map(rule => `
                        <li class="rule-item">
                            <span class="rule-type">${rule.entity}${rule.field ? '.' + rule.field : ''}</span>
                            ${rule.rule}
                        </li>
                    `).join('')}
                </ul>
            </div>
        `).join('');
    }

    private generateCoverageMetrics(analysis: AnalysisData): string {
        // Calculate metrics
        const totalSM = analysis.state_machines.length;
        const totalEntities = analysis.crud_analysis.length;
        const totalRules = analysis.business_rules.length;
        const totalQuestions = analysis.clarifying_questions.reduce(
            (sum, cat) => sum + cat.questions.length, 0
        );

        // Calculate coverage percentages
        let smCoverage = 100;
        if (totalSM > 0) {
            const totalTransitions = analysis.state_machines.reduce((sum, sm) =>
                sum + sm.transitions_found.length + sm.transitions_implied_but_missing.length, 0
            );
            const foundTransitions = analysis.state_machines.reduce((sum, sm) =>
                sum + sm.transitions_found.length, 0
            );
            smCoverage = totalTransitions > 0 ? (foundTransitions / totalTransitions * 100) : 100;
        }

        let crudCoverage = 100;
        if (totalEntities > 0) {
            const totalOps = totalEntities * 5;
            const missingOps = analysis.crud_analysis.reduce((sum, crud) =>
                sum + crud.missing_operations.length, 0
            );
            crudCoverage = ((totalOps - missingOps) / totalOps * 100);
        }

        return `
            <div class="summary">
                <div class="metric-card">
                    <h3>State Machines</h3>
                    <div class="metric-value">${totalSM}</div>
                    <div class="metric-label">Detected workflows</div>
                </div>
                <div class="metric-card">
                    <h3>Entities</h3>
                    <div class="metric-value">${totalEntities}</div>
                    <div class="metric-label">Data models found</div>
                </div>
                <div class="metric-card">
                    <h3>Business Rules</h3>
                    <div class="metric-value">${totalRules}</div>
                    <div class="metric-label">Rules extracted</div>
                </div>
                <div class="metric-card">
                    <h3>Questions</h3>
                    <div class="metric-value">${totalQuestions}</div>
                    <div class="metric-label">Clarifications needed</div>
                </div>
                <div class="metric-card">
                    <h3>SM Coverage</h3>
                    <div class="metric-value">${smCoverage.toFixed(0)}%</div>
                    <div class="metric-label">State transitions</div>
                </div>
                <div class="metric-card">
                    <h3>CRUD Coverage</h3>
                    <div class="metric-value">${crudCoverage.toFixed(0)}%</div>
                    <div class="metric-label">Operations defined</div>
                </div>
            </div>
        `;
    }

    private generateQuestionsPriorityChart(questions: QuestionCategory[]): string {
        if (!questions || questions.length === 0) {
            return '<p style="color: var(--fg-secondary);">No questions generated.</p>';
        }

        // Group by priority
        const high = questions.filter(q => q.priority === 'high').reduce((sum, q) => sum + q.questions.length, 0);
        const medium = questions.filter(q => q.priority === 'medium').reduce((sum, q) => sum + q.questions.length, 0);
        const low = questions.filter(q => q.priority === 'low').reduce((sum, q) => sum + q.questions.length, 0);

        return `
            <div class="section">
                <div class="chart-container">
                    <canvas id="questionsChart"></canvas>
                </div>

                <div class="legend">
                    <div class="legend-item">
                        <div class="legend-color" style="background: #f44336;"></div>
                        <span>High Priority: ${high}</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #ff9800;"></div>
                        <span>Medium Priority: ${medium}</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-color" style="background: #4caf50;"></div>
                        <span>Low Priority: ${low}</span>
                    </div>
                </div>

                ${questions.map(cat => `
                    <div class="section" style="margin-top: 20px;">
                        <h3>${cat.category} (${cat.priority})</h3>
                        <ul class="rule-list">
                            ${cat.questions.map((q, i) => `
                                <li class="rule-item">
                                    <strong>${i + 1}. ${q.q}</strong>
                                    <div style="margin-top: 8px; color: var(--fg-secondary);">
                                        Context: ${q.context}
                                    </div>
                                    <div style="margin-top: 5px; color: var(--fg-secondary);">
                                        Impacts: ${q.impacts}
                                    </div>
                                </li>
                            `).join('')}
                        </ul>
                    </div>
                `).join('')}
            </div>

            <script>
                // Create chart
                const ctx = document.getElementById('questionsChart');
                new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: ['High Priority', 'Medium Priority', 'Low Priority'],
                        datasets: [{
                            data: [${high}, ${medium}, ${low}],
                            backgroundColor: ['#f44336', '#ff9800', '#4caf50'],
                            borderWidth: 2,
                            borderColor: '#fff'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        plugins: {
                            legend: {
                                display: false
                            },
                            title: {
                                display: true,
                                text: 'Questions by Priority',
                                font: { size: 16 }
                            }
                        }
                    }
                });
            </script>
        `;
    }
}
