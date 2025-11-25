# VS Code Extension - Recommendations & Future Improvements

**Date**: 2025-11-23
**Current Version**: 0.4.0
**Status**: Production Ready with Improvement Opportunities

## Executive Summary

The DAZZLE VS Code extension is now production-ready after migration from development-only setup. However, there are several opportunities for enhancement to improve user experience, robustness, and feature completeness.

## Immediate Recommendations (High Priority)

### 1. Add CLI Detection and Auto-Installation Helper

**Problem**: Users may not realize they need to install DAZZLE CLI first

**Solution**: Implement smart detection and guidance

```typescript
async function detectDazzleInstallation(): Promise<{
    installed: boolean;
    version?: string;
    path?: string;
    installMethod?: 'pip' | 'homebrew' | 'dev' | 'unknown';
}> {
    // Try to run `dazzle --version`
    // Detect installation method
    // Return status
}

async function offerInstallation() {
    const status = await detectDazzleInstallation();
    if (!status.installed) {
        const choice = await vscode.window.showErrorMessage(
            'DAZZLE CLI not found. Would you like to install it?',
            'Install via pip',
            'Show Instructions',
            'Dismiss'
        );

        if (choice === 'Install via pip') {
            // Open terminal and run pip install dazzle
            const terminal = vscode.window.createTerminal('Install DAZZLE');
            terminal.show();
            terminal.sendText('pip install dazzle');
        }
    }
}
```

**Benefits**:
- Reduced friction for new users
- Better onboarding experience
- Fewer support requests

**Effort**: Medium (2-3 hours)

### 2. Implement Proper Version Checking

**Problem**: Extension may not be compatible with all CLI versions

**Solution**: Add version compatibility checking

```typescript
const MIN_REQUIRED_VERSION = '0.1.0';

async function checkVersionCompatibility(): Promise<boolean> {
    // Run `dazzle --version`
    // Parse version
    // Compare with MIN_REQUIRED_VERSION
    // Show warning if incompatible
}
```

**Benefits**:
- Prevent cryptic errors from version mismatches
- Guide users to upgrade when needed
- Better error messages

**Effort**: Low (1-2 hours)

### 3. Add Workspace Validation on Open

**Problem**: Users don't know if their workspace is a valid DAZZLE project

**Solution**: Show status bar indicator

```typescript
// Status bar item showing:
// ✓ DAZZLE (valid) - Green
// ⚠ DAZZLE (no manifest) - Yellow
// ✗ DAZZLE (errors) - Red

const statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Left
);
statusBarItem.command = 'dazzle.showProjectInfo';
statusBarItem.show();
```

**Benefits**:
- Immediate visual feedback
- Discoverability of features
- Quick access to project info

**Effort**: Low (1-2 hours)

## Medium Priority Recommendations

### 4. Add Code Snippets

**Problem**: Users have to remember DSL syntax

**Solution**: Create snippet file with common patterns

```json
{
  "entity": {
    "prefix": "entity",
    "body": [
      "entity ${1:EntityName} \"${2:Display Name}\":",
      "\tid: uuid pk",
      "\t${3:name}: str(200) required",
      "\tcreated_at: datetime auto_add",
      "\tupdated_at: datetime auto_update",
      "\t$0"
    ],
    "description": "Create a new entity"
  },
  "surface": {
    "prefix": "surface",
    "body": [
      "surface ${1:surface_name} \"${2:Display Name}\":",
      "\tuses entity ${3:EntityName}",
      "\tmode: ${4|list,detail,form|}",
      "\t",
      "\tsection main \"${5:Section Title}\":",
      "\t\tfield ${6:field_name} \"${7:Field Label}\"",
      "\t\t$0"
    ],
    "description": "Create a new surface"
  }
}
```

**Benefits**:
- Faster DSL authoring
- Reduced syntax errors
- Better developer experience

**Effort**: Low (2-3 hours)

**File**: `extensions/vscode/snippets/dazzle.json`

### 5. Improve Error Messages with Quick Fixes

**Problem**: Validation errors don't offer solutions

**Solution**: Implement code actions for common fixes

```typescript
// For error "Unknown entity 'User'"
// Offer quick fix: "Create entity 'User'"

vscode.languages.registerCodeActionsProvider('dazzle-dsl', {
    provideCodeActions(document, range, context) {
        const actions: vscode.CodeAction[] = [];

        for (const diagnostic of context.diagnostics) {
            if (diagnostic.message.includes('Unknown entity')) {
                const fix = new vscode.CodeAction(
                    'Create missing entity',
                    vscode.CodeActionKind.QuickFix
                );
                fix.command = {
                    command: 'dazzle.createEntity',
                    title: 'Create entity',
                    arguments: [extractEntityName(diagnostic.message)]
                };
                actions.push(fix);
            }
        }

        return actions;
    }
});
```

**Benefits**:
- Faster error resolution
- Better learning experience
- Professional IDE feel

**Effort**: Medium (4-6 hours)

### 6. Add File Templates

**Problem**: Users don't know how to structure DSL files

**Solution**: Add "New DSL File" command with templates

```typescript
vscode.commands.registerCommand('dazzle.newDslFile', async () => {
    const template = await vscode.window.showQuickPick([
        { label: 'Entity Module', description: 'Domain models and entities' },
        { label: 'Surface Module', description: 'UI surfaces and forms' },
        { label: 'Integration Module', description: 'External services' },
        { label: 'Complete Module', description: 'All-in-one with examples' }
    ]);

    // Create file with appropriate template
});
```

**Benefits**:
- Consistent project structure
- Faster project setup
- Best practices built-in

**Effort**: Low (2-3 hours)

### 7. Add Build Output Preview

**Problem**: Users can't see what will be generated

**Solution**: Add preview command for generated files

```typescript
vscode.commands.registerCommand('dazzle.previewBuild', async () => {
    const stack = await selectStack();
    const previewPanel = vscode.window.createWebviewPanel(
        'dazzle.preview',
        'DAZZLE Build Preview',
        vscode.ViewColumn.Two,
        {}
    );

    // Show tree view of files that will be generated
    // Allow clicking to preview individual files
    // "Generate" button to actually run build
});
```

**Benefits**:
- Confidence before generating
- Understanding of stack outputs
- Better debugging

**Effort**: High (6-8 hours)

## Lower Priority Enhancements

### 8. Semantic Syntax Highlighting

**Current**: TextMate grammar (regex-based)
**Better**: LSP-based semantic tokens

**Benefits**:
- More accurate highlighting
- Context-aware coloring
- Better visual distinction

**Effort**: Medium (4-6 hours)

### 9. Rename Refactoring

**Feature**: Rename entity across all files

**Implementation**: LSP `textDocument/rename` provider

**Benefits**:
- Safe refactoring
- Multi-file consistency
- Professional IDE feature

**Effort**: Medium (4-6 hours)

### 10. Workspace Symbols

**Feature**: Project-wide symbol search (Cmd+T)

**Implementation**: LSP `workspace/symbol` provider

**Benefits**:
- Quick navigation
- Project understanding
- Standard IDE feature

**Effort**: Low (2-3 hours)

### 11. Code Lens

**Feature**: Show usage counts and references

```
entity User "User":  [5 references] [2 surfaces] [1 integration]
```

**Benefits**:
- Visibility into usage
- Dead code detection
- Impact analysis

**Effort**: Medium (4-6 hours)

### 12. Formatting Provider

**Feature**: Auto-format DSL files

**Implementation**:
- Consistent indentation
- Align field definitions
- Sort sections

**Effort**: Medium (4-6 hours)

## Testing Recommendations

### Unit Tests

**Current**: None
**Needed**:
- Command handlers
- Diagnostics parsing
- LSP client initialization
- Path resolution

**Framework**: Mocha + Chai (VS Code standard)

**Priority**: High
**Effort**: High (8-10 hours)

### Integration Tests

**Needed**:
- End-to-end command testing
- LSP feature testing
- File watcher testing
- Multi-workspace testing

**Priority**: Medium
**Effort**: High (8-10 hours)

### Manual Testing Checklist

Create comprehensive test plan:
- [ ] Fresh installation on macOS
- [ ] Fresh installation on Windows
- [ ] Fresh installation on Linux
- [ ] With pip installation
- [ ] With homebrew installation
- [ ] With development installation
- [ ] All commands (validate, build, lint)
- [ ] All LSP features
- [ ] Error scenarios
- [ ] Multi-workspace scenarios

## Documentation Improvements

### 1. Add Screenshots

**Needed**:
- Syntax highlighting example
- Validation errors in Problems panel
- LSP hover tooltip
- Autocomplete in action
- Build command output

**Location**: `extensions/vscode/images/`

### 2. Create Video Walkthrough

**Content**:
- Installing DAZZLE
- Installing extension
- Creating first project
- Using validation
- Using LSP features
- Running build

**Platform**: YouTube or Vimeo
**Duration**: 3-5 minutes

### 3. Add Contribution Guide

**Content**:
- Extension architecture
- Development setup
- Testing procedures
- Release process
- Code style guide

**Location**: `extensions/vscode/CONTRIBUTING.md`

## Performance Optimizations

### 1. Lazy Load LLM Commands

**Current**: All LLM code loaded on activation
**Better**: Load only when needed

```typescript
// Dynamic import
const analyzeSpecCmd = vscode.commands.registerCommand('dazzle.analyzeSpec', async () => {
    const { analyzeSpec } = await import('./llmCommands');
    return analyzeSpec(context);
});
```

**Impact**: Faster activation time
**Effort**: Low (1 hour)

### 2. Debounce File Watcher

**Current**: Validates on every file change
**Better**: Debounce validation calls

```typescript
let validationTimeout: NodeJS.Timeout | undefined;

fileWatcher.onDidChange((uri) => {
    if (validationTimeout) {
        clearTimeout(validationTimeout);
    }
    validationTimeout = setTimeout(() => {
        validateCurrentWorkspace();
    }, 500); // 500ms debounce
});
```

**Impact**: Better performance during rapid edits
**Effort**: Low (30 minutes)

### 3. Cache Validation Results

**Current**: Re-validates entire project every time
**Better**: Cache results and invalidate smartly

**Impact**: Much faster validation
**Effort**: Medium (3-4 hours)

## Security Considerations

### 1. Validate CLI Paths

**Issue**: User-provided paths could be malicious
**Solution**: Validate before execution

```typescript
function isValidCliPath(path: string): boolean {
    // Check path doesn't contain shell injection
    // Verify file exists and is executable
    // Whitelist known safe paths
}
```

**Priority**: High
**Effort**: Low (1 hour)

### 2. Sanitize Workspace Paths

**Issue**: Malicious workspace could inject commands
**Solution**: Sanitize all paths used in shell commands

**Priority**: Medium
**Effort**: Low (1 hour)

## Release Checklist

Before publishing to marketplace:

- [ ] All high-priority recommendations implemented
- [ ] Extension tested on all platforms
- [ ] Unit tests added
- [ ] Documentation complete with screenshots
- [ ] Version bumped to 0.5.0
- [ ] CHANGELOG.md updated
- [ ] License file included
- [ ] README has marketplace badges
- [ ] Icon created (256x256 PNG)
- [ ] Publisher account created
- [ ] Extension packaged and validated
- [ ] Marketplace listing prepared

## Conclusion

The VS Code extension is functionally complete and production-ready. The recommendations above would enhance user experience, robustness, and feature parity with other professional language extensions.

**Recommended Implementation Order**:
1. CLI detection and auto-installation (#1)
2. Version checking (#2)
3. Code snippets (#4)
4. Status bar indicator (#3)
5. Unit tests
6. Quick fixes (#5)
7. Documentation improvements
8. Remaining features as needed

**Estimated Total Effort**: 40-60 hours for all high and medium priority items

**Next Immediate Actions**:
1. Test extension with actual users
2. Gather feedback
3. Implement top 3 recommendations
4. Publish to marketplace
