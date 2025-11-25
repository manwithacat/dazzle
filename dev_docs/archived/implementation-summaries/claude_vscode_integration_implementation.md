# Claude + VS Code Integration - Implementation Guide

## What We Built

A **TOS-compliant, non-intrusive integration** between the DAZZLE VS Code extension and Claude's VS Code extension that automates the SPEC.md → Working App workflow.

### Key Design Principles

✅ **No TOS violations** - Never automates chat inputs without user consent
✅ **User-initiated** - All automation requires explicit user action
✅ **Helpful notifications** - Guides users to the right workflow
✅ **Graceful degradation** - Works with or without Claude installed
✅ **Clipboard-based** - Safe, universal method for prompt transfer

---

## Features Implemented

### 1. **Auto-Detection of SPEC.md**

When you open a DAZZLE project with a SPEC.md file:

**Scenario A: Claude Extension Installed**
```
[Status Bar]  💡 Ask Claude to Generate App  (clickable)

[Notification after 3 seconds]
"💡 SPEC.md detected! Generate DAZZLE app with Claude?"
[Copy Prompt to Clipboard] [Open Claude Chat] [Not Now] [Don't Show Again]
```

**Scenario B: Claude Not Installed**
```
[Status Bar]  🧪 Generate DSL from SPEC  (clickable)

[Notification]
"💡 SPEC.md detected! Generate DSL from specification?"
[Run DAZZLE Analyze] [Install Claude Extension] [Not Now]
```

### 2. **One-Click Prompt Generation**

User clicks "Copy Prompt to Clipboard":
```
✓ Copied! A carefully crafted prompt is now in clipboard
✓ Just paste in Claude chat
✓ Claude automatically runs: analyze-spec → validate → build
✓ App is generated and ready to run
```

The generated prompt:
```
I have a SPEC.md file with my application requirements in this DAZZLE project.

Please help me transform this specification into a working application by:

1. Reading the SPEC.md file to understand the requirements
2. Using DAZZLE's LLM integration to generate DSL:
   `dazzle analyze-spec SPEC.md --no-interactive --generate-dsl`
3. Validating the generated DSL:
   `dazzle validate`
4. Building the application:
   `dazzle build --stack micro`
5. Showing me how to run the generated application

Please proceed with these steps automatically and report any issues you encounter.
```

### 3. **Smart Status Bar Indicator**

The status bar shows context-aware actions:

| State | Status Bar Shows |
|-------|-----------------|
| SPEC.md exists + DSL empty + Claude installed | `💡 Ask Claude to Generate App` |
| SPEC.md exists + DSL empty + No Claude | `🧪 Generate DSL from SPEC` |
| SPEC.md exists + DSL populated | (hidden) |
| No SPEC.md | (hidden) |

### 4. **Command Palette Integration**

```
Cmd/Ctrl + Shift + P

> DAZZLE: Generate from SPEC

Opens dialog:
[Copy Prompt to Clipboard] [Open Claude Chat] [Run DAZZLE Analyze]
```

### 5. **File Watchers**

The extension watches for:
- Creation of SPEC.md
- Changes to SPEC.md
- Changes to dsl/ directory

And automatically updates the status bar.

---

## How It Works (Technical Details)

### Architecture

```
┌─────────────────────────────────────────┐
│  DAZZLE VS Code Extension               │
├─────────────────────────────────────────┤
│                                         │
│  claudeIntegration.ts                   │
│  ├─ isClaudeInstalled()                 │
│  │  └─ Checks for Claude extension IDs  │
│  │                                       │
│  ├─ hasSpecFile()                       │
│  │  └─ Detects SPEC.md in workspace     │
│  │                                       │
│  ├─ isDSLEmpty()                        │
│  │  └─ Checks if DSL needs generation   │
│  │                                       │
│  ├─ generateClaudePrompt()              │
│  │  └─ Creates workflow prompt          │
│  │                                       │
│  ├─ showSpecDetectedNotification()      │
│  │  └─ Shows context-aware dialog       │
│  │                                       │
│  └─ copyPromptToClipboard()             │
│     └─ Uses VS Code clipboard API       │
│                                         │
└─────────────────────────────────────────┘
           ↓ User pastes
┌─────────────────────────────────────────┐
│  Claude VS Code Extension               │
│  (User's existing Claude subscription)  │
│                                         │
│  Executes:                              │
│  1. Reads SPEC.md                       │
│  2. Runs dazzle analyze-spec            │
│  3. Validates DSL                       │
│  4. Builds application                  │
│  5. Shows how to run                    │
└─────────────────────────────────────────┘
```

### Key Code Locations

**`claudeIntegration.ts`** (New file - 400+ lines)
- All Claude detection and integration logic
- TOS-compliant, user-initiated flows
- Clipboard-based prompt transfer

**`extension.ts`** (Modified)
- Integrated Claude detection on activation
- Status bar creation and updates
- File watching for SPEC.md

**`llmCommands.ts`** (Existing)
- `dazzle.analyzeSpec` command (direct analysis)
- Fallback if Claude not available

### Detection Logic

```typescript
// Check if Claude is installed
const CLAUDE_EXTENSION_IDS = [
    'anthropic.claude',           // Official extension
    'anthropic.claude-vscode',
    'anthropic.claude-code',
    'saoudrizwan.claude-dev',     // Community extension
];

function isClaudeInstalled() {
    for (const id of CLAUDE_EXTENSION_IDS) {
        if (vscode.extensions.getExtension(id)) {
            return { installed: true, extensionId: id };
        }
    }
    return { installed: false };
}
```

### SPEC.md Detection

```typescript
function hasSpecFile(workspaceRoot: string) {
    const patterns = ['SPEC.md', 'spec.md', 'SPECIFICATION.md'];

    for (const pattern of patterns) {
        const path = join(workspaceRoot, pattern);
        if (exists(path)) {
            return { exists: true, path };
        }
    }

    return { exists: false };
}
```

### DSL State Detection

```typescript
function isDSLEmpty(workspaceRoot: string): boolean {
    const dslDir = join(workspaceRoot, 'dsl');

    if (!exists(dslDir)) return true;

    const files = readdirSync(dslDir);

    // Empty if no files
    if (files.length === 0) return true;

    // Empty if only template file
    if (files.length === 1 && files[0] === 'app.dsl') {
        const content = readFileSync(join(dslDir, 'app.dsl'), 'utf-8');
        const isTemplate = content.includes('# Define your entities');
        return isTemplate;
    }

    return false;
}
```

---

## User Experience Flow

### Happy Path (Claude Installed)

1. **User opens project in VS Code**
   ```
   code /Volumes/SSD/test
   ```

2. **DAZZLE extension activates** (3 seconds later)
   ```
   [Notification]
   "💡 SPEC.md detected! Generate DAZZLE app with Claude?"
   ```

3. **User clicks "Copy Prompt to Clipboard"**
   ```
   ✓ Prompt copied to clipboard
   ✓ "Prompt copied! Paste in Claude chat to generate your app."
   ```

4. **User opens Claude** (Cmd+Shift+I or via panel)
   ```
   [Claude Chat Panel Opens]
   ```

5. **User pastes** (Cmd+V)
   ```
   Claude: "I'll help you transform your SPEC.md into a working application.
           Let me start by reading your SPEC.md file..."

   [Claude executes commands]
   - dazzle analyze-spec SPEC.md --no-interactive --generate-dsl
   - dazzle validate
   - dazzle build --stack micro

   Claude: "✓ Your Urban Canopy application is ready!
           Navigate to build/test/ to run it.

           Next steps:
           cd build/test
           pip install -r requirements.txt
           python manage.py migrate
           python manage.py runserver

           Your app will be at http://localhost:8000"
   ```

6. **Total time**: ~2 minutes from opening project to running app
7. **User actions**: 3 clicks (Copy Prompt, Open Claude, Paste)

### Alternative Path (No Claude)

1. User clicks "Run DAZZLE Analyze"
2. Extension runs `dazzle.analyzeSpec` command directly
3. Shows UI for Q&A workflow
4. Generates DSL
5. User runs `dazzle build` manually

---

## TOS Compliance

### What We DO ✅

✅ **Detect Claude extension** - Public VS Code API
✅ **Show notifications** - Standard VS Code UX
✅ **Copy to clipboard** - User-initiated action
✅ **Open chat (if API available)** - Checks for exposed commands
✅ **Provide helpful prompts** - Documentation, not automation

### What We DON'T ❌

❌ **Auto-send messages** - Never sends to Claude without user paste
❌ **Bypass user interaction** - All flows require user clicks
❌ **Inject code** - No manipulation of Claude's extension
❌ **Simulate typing** - No programmatic input simulation
❌ **Access Claude's internals** - Only public APIs

### Safe Integration Methods Used

1. **Extension Detection** (`vscode.extensions.getExtension`)
   - Standard VS Code API
   - Read-only check
   - No extension manipulation

2. **Command Execution** (`vscode.commands.executeCommand`)
   - Only if commands are publicly exposed
   - Graceful fallback if not available
   - User sees what's happening

3. **Clipboard API** (`vscode.env.clipboard.writeText`)
   - Standard VS Code API
   - User explicitly requests copy
   - User controls paste action

4. **Notifications** (`vscode.window.showInformationMessage`)
   - Standard VS Code UX
   - User can dismiss or disable
   - Clear action buttons

---

## Testing the Integration

### Test Environment Setup

```bash
# 1. Build the updated extension
cd /Volumes/SSD/Dazzle/extensions/vscode
npm run compile

# 2. Package the extension
npm run package

# 3. Install in VS Code
code --install-extension dazzle-dsl-0.4.0.vsix
```

### Test Case 1: Claude Installed + SPEC.md Exists

```bash
# Setup
code /Volumes/SSD/test

# Expected behavior:
# 1. Extension activates
# 2. After 3 seconds: Notification appears
#    "💡 SPEC.md detected! Generate DAZZLE app with Claude?"
# 3. Status bar shows: "💡 Ask Claude to Generate App"
# 4. Click "Copy Prompt to Clipboard"
# 5. Prompt is copied
# 6. Open Claude chat
# 7. Paste
# 8. Claude executes workflow
```

### Test Case 2: Claude Not Installed

```bash
# Setup
# 1. Uninstall Claude extension temporarily
code --uninstall-extension anthropic.claude

# 2. Open project
code /Volumes/SSD/test

# Expected behavior:
# 1. Notification shows: "Generate DSL from specification?"
# 2. Status bar shows: "🧪 Generate DSL from SPEC"
# 3. Click "Run DAZZLE Analyze"
# 4. Opens analyze-spec UI
```

### Test Case 3: SPEC.md Created After Opening

```bash
# Setup
code /Volumes/SSD/empty-project

# In VS Code, create SPEC.md

# Expected behavior:
# 1. File watcher detects creation
# 2. Status bar updates
# 3. Notification appears (if enabled)
```

### Test Case 4: DSL Already Generated

```bash
# Setup
# 1. Generate DSL first
cd /Volumes/SSD/test
dazzle analyze-spec SPEC.md --no-interactive --generate-dsl

# 2. Open in VS Code
code /Volumes/SSD/test

# Expected behavior:
# 1. Status bar hidden (DSL already exists)
# 2. No notification (nothing to generate)
```

---

## Configuration Options

Users can customize behavior in VS Code settings:

```json
{
  // Enable/disable auto-detection
  "dazzle.claude.autoDetect": true,

  // Show notifications when SPEC.md is detected
  "dazzle.claude.showNotifications": true,

  // Prefer Claude for generation (vs. direct CLI)
  "dazzle.claude.preferClaudeForGeneration": true
}
```

---

## Future Enhancements

### Phase 2: VS Code Chat API Integration (VS Code 1.85+)

If Claude exposes itself via VS Code's chat API:

```typescript
// Check for VS Code Chat API
if (vscode.chat) {
    const participants = vscode.chat.participants;
    const claude = participants.find(p => p.id.includes('claude'));

    if (claude) {
        // Send message via Chat API
        await vscode.chat.sendRequest(claude.id, {
            prompt: generateClaudePrompt(specPath)
        });
    }
}
```

### Phase 3: Claude MCP Server

Create a Model Context Protocol server for DAZZLE:

```json
{
  "name": "dazzle-mcp",
  "version": "1.0.0",
  "tools": [
    {
      "name": "analyze_spec",
      "description": "Analyze SPEC.md and generate DSL",
      "inputSchema": { "type": "object", "properties": { "path": "string" } }
    },
    {
      "name": "validate_dsl",
      "description": "Validate DAZZLE DSL files"
    },
    {
      "name": "build_app",
      "description": "Build application from DSL",
      "inputSchema": { "stack": "string" }
    }
  ]
}
```

Then Claude desktop app can call:
```
use_mcp_tool("analyze_spec", { "path": "SPEC.md" })
```

---

## Troubleshooting

### "Notification doesn't appear"

**Check**:
1. Is SPEC.md in project root?
2. Is DSL directory empty?
3. Did you disable notifications?

**Fix**:
```typescript
// Reset notification preference
// Command Palette > Developer: Reset Extension State
```

### "Claude not detected"

**Check**:
1. Is Claude extension installed?
   ```
   code --list-extensions | grep claude
   ```

**Fix**:
```bash
# Install from marketplace
code --install-extension anthropic.claude
```

### "Prompt doesn't work in Claude"

**Check**:
1. Did you set ANTHROPIC_API_KEY? (Not needed for Claude extension subscription)
2. Is Claude's subscription active?

**Fix**:
- Claude extension uses logged-in subscription
- No API key needed
- Just paste the prompt

---

## Summary

### What This Achieves

✅ **Zero-config integration** - Works out of the box
✅ **TOS-compliant** - User-initiated, clipboard-based
✅ **Seamless UX** - 3 clicks from SPEC to running app
✅ **Safe fallback** - Works without Claude
✅ **Non-intrusive** - Can be disabled

### The Magic

The integration doesn't "automate" Claude - it **guides the user** to the right workflow with **pre-crafted prompts** that Claude can execute.

This is more powerful than direct automation because:
- Claude can handle errors naturally
- Claude can ask clarifying questions
- Claude provides explanations
- No API key management needed
- Uses user's existing Claude subscription

### Comparison to Direct Integration

| Approach | Pros | Cons |
|----------|------|------|
| **Direct API calls** | Fully automated | Requires API keys, Error handling, Token management, Cost |
| **Claude orchestration** (our approach) | Free with subscription, Error recovery, Conversational, TOS-compliant | Requires one paste |

The one-paste approach is the sweet spot: minimal friction, maximum capability.

---

**Implementation Status**: ✅ Complete
**Testing**: Ready for user testing
**Next Step**: Compile and install extension in VS Code
