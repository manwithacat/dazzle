# VS Code Extension Simplification (Nov 24, 2025)

## Context

The DAZZLE VS Code extension had become complex, brittle, and difficult to test due to:
- Complex LLM integration with interactive Q&A dialogs
- Custom UI panels and analysis dashboards
- Multiple layers of file watching and detection logic
- Over-engineered Claude integration attempts

User's goal: Provide IDE developers a way to use their own Claude subscription (tokens) to work with DAZZLE projects, with minimal complexity.

## Changes Made

### Removed (711+ lines deleted)

1. **`src/llmCommands.ts`** (313 lines) - Complex spec analysis with:
   - Interactive Q&A dialogs
   - Process spawning and JSON parsing
   - Cost estimation and confirmation flows
   - Terminal-based DSL generation

2. **`src/ui/analysisPanel.ts`** (entire directory) - Custom UI:
   - Webview-based analysis dashboard
   - State machine visualization
   - CRUD analysis displays

3. **Complex logic from `claudeIntegration.ts`** (reduced 398 → 241 lines):
   - Multiple fallback approaches for opening Claude chat
   - File watching for SPEC.md changes
   - isDSLEmpty complexity
   - Attempted automation of Claude extension

### Simplified (241 lines remaining)

**`src/claudeIntegration.ts`** now provides:

1. **Simple Claude detection** - checks for known extension IDs
2. **SPEC.md detection** - finds specification files
3. **Pre-crafted prompt templates** for 4 workflows:
   - Analyze SPEC → Generate DSL → Build
   - Validate & Fix errors
   - Build with stack selection
   - Initialize new project
4. **Clipboard-based handoff** - copy prompt, user pastes in Claude
5. **Status bar indication** - shows when SPEC.md exists without DSL
6. **One-time notification** - helpful first-time user guidance

### Commands Updated

**Removed:**
- `dazzle.analyzeSpec` (complex interactive flow)

**Added:**
- `dazzle.askClaudeToAnalyze` - Copy SPEC analysis prompt
- `dazzle.askClaudeToFix` - Copy validation fix prompt
- `dazzle.askClaudeToBuild` - Copy build prompt (with stack picker)
- `dazzle.askClaudeToInit` - Copy initialization prompt

## Architecture

### Current Pattern (Clipboard-based handoff)

This is the **recommended pattern** for Claude Code integration:

```
User clicks command
  ↓
Extension generates prompt
  ↓
Prompt copied to clipboard
  ↓
User pastes in Claude chat
  ↓
Claude executes workflow (using their tokens)
```

**Why this works:**
- User explicitly initiates (TOS compliant)
- Uses user's Claude subscription
- No API key management in extension
- Simple, testable code
- Works with any Claude extension variant

### Prompt Template Example

```typescript
const PROMPTS = {
  analyzeSpec: (specPath: string) => `I have a SPEC.md file in this DAZZLE project.

Please help me transform this specification into a working application:

1. Read ${specPath}
2. Run: dazzle analyze-spec ${specPath} --no-interactive --generate-dsl
3. Run: dazzle validate
4. Run: dazzle build --stack micro
5. Show me how to run the generated application

Proceed automatically and report any issues you encounter.`
};
```

## Benefits

1. **Simplicity**: 241 lines vs 711+ lines
2. **Testability**: Minimal UI interactions, pure functions
3. **Reliability**: No process spawning, no complex error handling
4. **Maintainability**: Clear, focused code
5. **User control**: They use their Claude subscription
6. **Extensibility**: Easy to add new prompt templates

## Testing

- ✅ Extension compiles without errors
- ✅ No stale compiled files
- ✅ All new commands registered in package.json
- ✅ LSP and diagnostic features unchanged

## Future: MCP Server

The logical next step is implementing a **Model Context Protocol (MCP) server** for DAZZLE:

**Benefits:**
- Claude Code can call DAZZLE commands directly
- No clipboard copy/paste needed
- Tighter integration
- Better UX for complex workflows

**Scope:**
- Expose DAZZLE CLI commands as MCP tools
- Add DAZZLE-specific context (entities, surfaces, etc.)
- Enable interactive spec updates via AI

**Vision:**
Founders have conversations with their AI → deliver markdown spec → AI writes DSL using DAZZLE grammar → they pay for their own tokens.

## Files Changed

- `extensions/vscode/src/claudeIntegration.ts` - Simplified (398 → 241 lines)
- `extensions/vscode/src/extension.ts` - Updated imports and activation
- `extensions/vscode/package.json` - Updated command definitions
- **Deleted:**
  - `extensions/vscode/src/llmCommands.ts`
  - `extensions/vscode/src/ui/analysisPanel.ts`

## Metrics

- **Lines removed**: 711+
- **Lines added**: 241
- **Net reduction**: 470+ lines (~66% reduction)
- **Complexity reduction**: Significant (removed process spawning, UI panels, complex state)
- **Compilation**: ✅ Clean
- **Commands**: 4 new simple commands vs 1 complex command

## Outcome

The extension is now:
- **Focused**: Language support + LSP + simple Claude handoff
- **Testable**: Pure functions, minimal side effects
- **Maintainable**: Clear separation of concerns
- **User-friendly**: Pre-crafted prompts for common tasks
- **Flexible**: Easy to extend with new prompts

Ready for initial users to test the simplified workflow.
