// @ts-check
"use strict";

/**
 * Task Header Component
 *
 * Renders task information and outcome buttons when a surface is
 * displayed as part of a human task workflow.
 */

/**
 * @typedef {Object} TaskOutcome
 * @property {string} name - Outcome identifier
 * @property {string} label - Button label
 * @property {string} style - Button style (primary, danger, secondary, warning)
 * @property {string|null} confirm - Confirmation prompt
 */

/**
 * @typedef {Object} TaskContext
 * @property {string} task_id
 * @property {string} process_name
 * @property {string} process_run_id
 * @property {string} step_name
 * @property {string} surface_name
 * @property {string} entity_name
 * @property {string} entity_id
 * @property {string} due_at
 * @property {string} time_remaining
 * @property {string} urgency
 * @property {boolean} is_overdue
 * @property {boolean} is_escalated
 * @property {string|null} assignee_id
 * @property {string|null} assignee_role
 * @property {TaskOutcome[]} outcomes
 */

/**
 * Initialize task header if task context is present.
 * Call this after page load.
 */
export function initTaskHeader() {
    const taskContextEl = document.getElementById('task-context');
    if (!taskContextEl) return;

    try {
        const taskContext = JSON.parse(taskContextEl.textContent || '{}');
        if (taskContext.task_id) {
            renderTaskHeader(taskContext);
        }
    } catch (e) {
        console.error('Failed to parse task context:', e);
    }
}

/**
 * Render task header with info and outcome buttons.
 * @param {TaskContext} taskContext
 */
export function renderTaskHeader(taskContext) {
    const container = document.querySelector('.surface-container, .page-content, main');
    if (!container) {
        console.warn('No container found for task header');
        return;
    }

    // Create header element
    const header = createTaskHeaderElement(taskContext);
    container.insertBefore(header, container.firstChild);

    // Create footer with outcome buttons
    const footer = createTaskFooterElement(taskContext);
    container.appendChild(footer);

    // Add task styles if not present
    addTaskStyles();
}

/**
 * Create the task header element.
 * @param {TaskContext} taskContext
 * @returns {HTMLElement}
 */
function createTaskHeaderElement(taskContext) {
    const header = document.createElement('div');
    header.className = 'task-header';
    header.setAttribute('data-urgency', taskContext.urgency);

    const urgencyIcon = getUrgencyIcon(taskContext.urgency);
    const statusBadge = taskContext.is_escalated
        ? '<span class="task-badge escalated">Escalated</span>'
        : '';

    header.innerHTML = `
        <div class="task-header-content">
            <div class="task-info">
                <span class="task-icon">${urgencyIcon}</span>
                <div class="task-details">
                    <span class="task-label">Task: ${escapeHtml(taskContext.step_name)}</span>
                    <span class="task-process">Process: ${escapeHtml(taskContext.process_name)}</span>
                </div>
            </div>
            <div class="task-timing">
                <span class="task-due ${taskContext.is_overdue ? 'overdue' : ''}">
                    ${taskContext.is_overdue ? 'Overdue' : `Due in ${taskContext.time_remaining}`}
                </span>
                ${statusBadge}
            </div>
        </div>
    `;

    return header;
}

/**
 * Create the task footer with outcome buttons.
 * @param {TaskContext} taskContext
 * @returns {HTMLElement}
 */
function createTaskFooterElement(taskContext) {
    const footer = document.createElement('div');
    footer.className = 'task-footer';

    const buttonsContainer = document.createElement('div');
    buttonsContainer.className = 'task-outcomes';

    taskContext.outcomes.forEach(outcome => {
        const btn = createOutcomeButton(taskContext.task_id, outcome);
        buttonsContainer.appendChild(btn);
    });

    footer.appendChild(buttonsContainer);
    return footer;
}

/**
 * Create an outcome button.
 * @param {string} taskId
 * @param {TaskOutcome} outcome
 * @returns {HTMLButtonElement}
 */
function createOutcomeButton(taskId, outcome) {
    const btn = document.createElement('button');
    btn.className = `btn btn-${outcome.style} task-outcome-btn`;
    btn.textContent = outcome.label;
    btn.setAttribute('data-outcome', outcome.name);

    btn.addEventListener('click', () => handleOutcome(taskId, outcome));

    return btn;
}

/**
 * Handle outcome button click.
 * @param {string} taskId
 * @param {TaskOutcome} outcome
 */
async function handleOutcome(taskId, outcome) {
    // Show confirmation if required
    if (outcome.confirm) {
        const confirmed = confirm(outcome.confirm);
        if (!confirmed) return;
    }

    // Disable all outcome buttons
    const buttons = document.querySelectorAll('.task-outcome-btn');
    buttons.forEach(btn => {
        btn.setAttribute('disabled', 'true');
    });

    try {
        const response = await fetch(`/api/tasks/${taskId}/complete`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ outcome: outcome.name }),
        });

        if (response.ok) {
            showTaskSuccess(outcome.label);
            // Redirect to task list or previous page after short delay
            setTimeout(() => {
                const returnUrl = getReturnUrl();
                window.location.href = returnUrl;
            }, 1500);
        } else {
            const error = await response.json();
            showTaskError(error.detail || 'Failed to complete task');
            // Re-enable buttons
            buttons.forEach(btn => btn.removeAttribute('disabled'));
        }
    } catch (e) {
        console.error('Error completing task:', e);
        showTaskError(`Error: ${e instanceof Error ? e.message : 'Unknown error'}`);
        // Re-enable buttons
        buttons.forEach(btn => btn.removeAttribute('disabled'));
    }
}

/**
 * Show success message after task completion.
 * @param {string} outcomeLabel
 */
function showTaskSuccess(outcomeLabel) {
    const footer = document.querySelector('.task-footer');
    if (footer) {
        footer.innerHTML = `
            <div class="task-success">
                <span class="success-icon">✓</span>
                <span class="success-message">Task completed: ${escapeHtml(outcomeLabel)}</span>
            </div>
        `;
    }
}

/**
 * Show error message.
 * @param {string} message
 */
function showTaskError(message) {
    const footer = document.querySelector('.task-footer');
    if (footer) {
        const errorEl = document.createElement('div');
        errorEl.className = 'task-error';
        errorEl.textContent = message;

        // Insert before buttons
        const outcomes = footer.querySelector('.task-outcomes');
        if (outcomes) {
            footer.insertBefore(errorEl, outcomes);
        } else {
            footer.appendChild(errorEl);
        }

        // Remove after 5 seconds
        setTimeout(() => errorEl.remove(), 5000);
    }
}

/**
 * Get return URL after task completion.
 * @returns {string}
 */
function getReturnUrl() {
    // Check for return_url in query params
    const params = new URLSearchParams(window.location.search);
    const returnUrl = params.get('return_url');
    if (returnUrl) return returnUrl;

    // Default to task inbox
    return '/workspaces/tasks';
}

/**
 * Get icon for urgency level.
 * @param {string} urgency
 * @returns {string}
 */
function getUrgencyIcon(urgency) {
    switch (urgency) {
        case 'critical':
            return '🔴';
        case 'high':
            return '🟠';
        case 'medium':
            return '🟡';
        default:
            return '🟢';
    }
}

/**
 * Escape HTML to prevent XSS.
 * @param {string} text
 * @returns {string}
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Add task-specific styles to the page.
 */
function addTaskStyles() {
    if (document.getElementById('task-header-styles')) return;

    const styles = document.createElement('style');
    styles.id = 'task-header-styles';
    styles.textContent = `
        .task-header {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            border: 1px solid #dee2e6;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }

        .task-header[data-urgency="critical"] {
            border-left: 4px solid #dc3545;
            background: linear-gradient(135deg, #fff5f5 0%, #ffe3e3 100%);
        }

        .task-header[data-urgency="high"] {
            border-left: 4px solid #fd7e14;
            background: linear-gradient(135deg, #fff8f0 0%, #ffe8cc 100%);
        }

        .task-header[data-urgency="medium"] {
            border-left: 4px solid #ffc107;
        }

        .task-header-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }

        .task-info {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .task-icon {
            font-size: 24px;
        }

        .task-details {
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .task-label {
            font-weight: 600;
            font-size: 16px;
            color: #212529;
        }

        .task-process {
            font-size: 14px;
            color: #6c757d;
        }

        .task-timing {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .task-due {
            font-size: 14px;
            color: #495057;
            padding: 4px 12px;
            background: white;
            border-radius: 16px;
            border: 1px solid #dee2e6;
        }

        .task-due.overdue {
            background: #dc3545;
            color: white;
            border-color: #dc3545;
            font-weight: 600;
        }

        .task-badge {
            font-size: 12px;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 500;
        }

        .task-badge.escalated {
            background: #fd7e14;
            color: white;
        }

        .task-footer {
            margin-top: 24px;
            padding-top: 16px;
            border-top: 1px solid #dee2e6;
        }

        .task-outcomes {
            display: flex;
            gap: 12px;
            justify-content: flex-end;
            flex-wrap: wrap;
        }

        .task-outcome-btn {
            padding: 10px 24px;
            font-size: 15px;
            font-weight: 500;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .task-outcome-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        .task-outcome-btn.btn-primary {
            background: #0d6efd;
            border: 1px solid #0d6efd;
            color: white;
        }

        .task-outcome-btn.btn-primary:hover:not(:disabled) {
            background: #0b5ed7;
        }

        .task-outcome-btn.btn-danger {
            background: #dc3545;
            border: 1px solid #dc3545;
            color: white;
        }

        .task-outcome-btn.btn-danger:hover:not(:disabled) {
            background: #bb2d3b;
        }

        .task-outcome-btn.btn-secondary {
            background: #6c757d;
            border: 1px solid #6c757d;
            color: white;
        }

        .task-outcome-btn.btn-secondary:hover:not(:disabled) {
            background: #5c636a;
        }

        .task-outcome-btn.btn-warning {
            background: #ffc107;
            border: 1px solid #ffc107;
            color: #212529;
        }

        .task-outcome-btn.btn-warning:hover:not(:disabled) {
            background: #ffca2c;
        }

        .task-success {
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            padding: 16px;
            background: #d1e7dd;
            border-radius: 8px;
            color: #0f5132;
        }

        .success-icon {
            font-size: 24px;
        }

        .success-message {
            font-size: 16px;
            font-weight: 500;
        }

        .task-error {
            background: #f8d7da;
            color: #842029;
            padding: 12px 16px;
            border-radius: 6px;
            margin-bottom: 12px;
            font-size: 14px;
        }

        @media (max-width: 576px) {
            .task-header-content {
                flex-direction: column;
                align-items: flex-start;
            }

            .task-outcomes {
                width: 100%;
                justify-content: stretch;
            }

            .task-outcome-btn {
                flex: 1;
                text-align: center;
            }
        }
    `;

    document.head.appendChild(styles);
}

// Auto-initialize on DOMContentLoaded
if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTaskHeader);
    } else {
        initTaskHeader();
    }
}
