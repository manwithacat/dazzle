# VS Code + Claude Integration Guide

This document explains how DAZZLE integrates with Claude in VS Code and outlines the current UX flow vs. potential future enhancements.

## Current Setup (v0.1.0)

### What Works TODAY ✅

**1. LLM Context Files**
When you run `dazzle init`, these files are created:
- `.claude/PROJECT_CONTEXT.md` - Guides Claude on DAZZLE workflows
- `.claude/WORKFLOW_SPEC_TO_APP.md` - Step-by-step SPEC → App instructions
- `.claude/permissions.json` - Claude Code permissions
- `LLM_CONTEXT.md` - General project overview
- `.llm/DAZZLE_PRIMER.md` - Detailed DAZZLE concepts

**2. Claude Can Execute Commands**
With Claude in VS Code (or Claude desktop app), Claude can:
- ✅ Read `SPEC.md` and understand requirements
- ✅ Execute `dazzle analyze-spec SPEC.md` to generate DSL
- ✅ Run `dazzle validate` to check DSL
- ✅ Run `dazzle build` to generate app
- ✅ Navigate to build directory and run the app
- ✅ Make edits to DSL files based on user feedback
- ✅ Debug validation errors and fix them

**3. Workflow: SPEC.md → Working App**

Current UX flow:
```
User: "I have a SPEC.md. Generate the app."
  ↓
Claude reads .claude/PROJECT_CONTEXT.md
  ↓
Claude sees SPEC.md exists
  ↓
Claude reads .claude/WORKFLOW_SPEC_TO_APP.md
  ↓
Claude executes:
  1. dazzle analyze-spec SPEC.md --no-interactive --generate-dsl
  2. dazzle validate
  3. dazzle build --stack micro
  4. cd build/test && pip install -r requirements.txt
  5. python manage.py migrate && python manage.py runserver
  ↓
User sees: Working app at http://localhost:8000
```

**4. Prerequisites**
- User has Claude subscription (for Claude in VS Code)
- User has `ANTHROPIC_API_KEY` set in environment
- User has DAZZLE installed with LLM support: `pip install 'dazzle[llm]'`

## How to Use (Step by Step)

### Option A: Let Claude Drive (Recommended)

1. **Create project with SPEC.md**:
   ```bash
   cd /Volumes/SSD/test
   # Edit your SPEC.md with requirements
   ```

2. **Open in VS Code with Claude**:
   ```bash
   code /Volumes/SSD/test
   ```

3. **Ask Claude** (in VS Code chat):
   ```
   I have a SPEC.md file with my application requirements.
   Please generate the DAZZLE DSL and build the application.
   ```

4. **Claude will**:
   - Detect SPEC.md exists
   - Read `.claude/WORKFLOW_SPEC_TO_APP.md`
   - Execute the workflow automatically
   - Report progress and results
   - Provide next steps

### Option B: Manual Commands (More Control)

1. **Analyze SPEC**:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   dazzle analyze-spec SPEC.md --no-interactive --generate-dsl
   ```

2. **Review & Validate**:
   ```bash
   cat dsl/generated.dsl  # Review what was generated
   dazzle validate        # Check for errors
   ```

3. **Build**:
   ```bash
   dazzle build --stack micro  # Or django_api, express_micro, etc.
   ```

4. **Run**:
   ```bash
   cd build/your-project
   # Follow stack-specific instructions
   ```

## What's NOT Automated (Yet)

### Current Limitations

1. **No VS Code Command Palette Integration**
   - Can't do: "Right-click SPEC.md → Generate DAZZLE App"
   - Must: Ask Claude in chat to do it
   - **Workaround**: Use Claude in VS Code chat

2. **No Visual Feedback in VS Code UI**
   - Can't: See progress bar for DSL generation
   - Must: Watch terminal output from Claude's commands
   - **Workaround**: Claude narrates progress in chat

3. **No Direct API Integration in Extension**
   - The DAZZLE VS Code extension doesn't call Anthropic APIs directly
   - Must: Use `dazzle analyze-spec` CLI command
   - **Workaround**: Claude executes CLI commands for you

4. **No Interactive Forms**
   - Can't: Fill out a form in VS Code to customize generation
   - Must: Edit SPEC.md or DSL manually
   - **Workaround**: Use `dazzle analyze-spec` interactive mode, or edit DSL after generation

## Future Enhancement Options

### Option 1: Enhanced VS Code Extension (Moderate Effort)

Add to DAZZLE VS Code extension:
```javascript
// New commands:
- "DAZZLE: Generate from SPEC.md"
- "DAZZLE: Analyze Spec (Interactive)"
- "DAZZLE: Build Application"
- "DAZZLE: Validate DSL"

// These would:
- Call dazzle CLI commands in background
- Show progress in VS Code UI
- Display results in output panel
- Offer quick fixes for validation errors
```

**Pros**: Native VS Code integration, no external dependencies
**Cons**: Still requires `dazzle analyze-spec` CLI (which uses LLM APIs)

### Option 2: MCP Server for Claude (Low Effort, High Impact)

Create a Model Context Protocol server for DAZZLE:
```javascript
// dazzle-mcp-server
{
  "tools": [
    "analyze_spec",    // Parse SPEC.md → DSL
    "validate_dsl",    // Validate DSL files
    "build_app",       // Generate artifacts
    "inspect_schema"   // Show AppSpec structure
  ]
}
```

**Pros**: Claude desktop app gets native DAZZLE tools
**Cons**: Requires MCP server implementation (~200 lines)

### Option 3: VS Code Webview UI (High Effort)

Create interactive UI in VS Code:
- SPEC.md → DSL wizard with Q&A
- Visual DSL editor (drag-drop entities, surfaces)
- Real-time validation feedback
- One-click "Build & Run"

**Pros**: Beautiful UX, no command line needed
**Cons**: Significant dev effort, maintenance burden

## Recommended Approach

For now (**v0.1.0**), the **Claude-in-VS-Code** approach is optimal:

### Why This Works Well

1. ✅ **Zero code changes needed** - Works with current DAZZLE
2. ✅ **Conversational UX** - Natural language instead of forms
3. ✅ **Flexible** - Can handle edge cases and clarifications
4. ✅ **Debuggable** - Claude explains what went wrong
5. ✅ **Extensible** - Easy to add new workflows to `.claude/`

### What Makes It Seamless

The `.claude/` context files make Claude **proactive**:
- Detects SPEC.md automatically
- Knows to run `analyze-spec` without being told
- Handles errors and suggests fixes
- Validates and builds in sequence
- Reports results clearly

### User Experience Flow

```
User opens project in VS Code
  ↓
Claude reads .claude/PROJECT_CONTEXT.md
  ↓
Claude sees: "⚠️ SPEC.md exists, DSL empty"
  ↓
Claude suggests: "I see you have requirements in SPEC.md.
                  Would you like me to generate the DSL and build the app?"
  ↓
User: "Yes"
  ↓
Claude: [Shows progress, runs commands, reports success]
  ↓
App is running at http://localhost:8000
```

## Testing the Integration

### Test Project Setup

1. **Create test project**:
   ```bash
   cd /Volumes/SSD/test
   # Your SPEC.md already exists
   ```

2. **Verify context files**:
   ```bash
   ls .claude/
   # Should show:
   # - PROJECT_CONTEXT.md
   # - WORKFLOW_SPEC_TO_APP.md
   # - permissions.json
   ```

3. **Open in VS Code with Claude**:
   ```bash
   code /Volumes/SSD/test
   ```

4. **Test Claude's awareness**:
   Ask: "What files are in this project?"
   Claude should mention SPEC.md and recognize it as input.

5. **Test the workflow**:
   Ask: "Generate the application from SPEC.md"
   Claude should execute the full workflow.

### Expected Results

✅ Claude reads SPEC.md
✅ Claude runs `dazzle analyze-spec SPEC.md --no-interactive --generate-dsl`
✅ Claude validates with `dazzle validate`
✅ Claude builds with `dazzle build`
✅ Claude shows you how to run the app
✅ Urban Canopy app is accessible at http://localhost:8000

## Troubleshooting

### Claude doesn't detect SPEC.md workflow

**Problem**: Claude doesn't suggest the SPEC → App workflow
**Solution**:
1. Check `.claude/PROJECT_CONTEXT.md` has the SPEC.md detection logic
2. Explicitly ask: "Please read .claude/WORKFLOW_SPEC_TO_APP.md and generate my app"
3. Verify Claude can read files in `.claude/` directory

### analyze-spec fails with API key error

**Problem**: `ANTHROPIC_API_KEY environment variable not set`
**Solution**:
```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...

# Or add to ~/.zshrc:
echo 'export ANTHROPIC_API_KEY=sk-ant-...' >> ~/.zshrc
source ~/.zshrc
```

### Generated DSL has validation errors

**Problem**: `dazzle validate` shows errors after generation
**Solution**:
1. Read error messages carefully
2. Ask Claude: "Fix the validation errors in dsl/generated.dsl"
3. Claude will edit the DSL and re-validate
4. When fixed, Claude will run `dazzle build`

### Build generates wrong stack

**Problem**: App is Django but user wanted Express
**Solution**:
```bash
# Rebuild with specific stack:
dazzle build --stack express_micro --force

# Or update dazzle.toml:
[stack]
name = "express_micro"
```

## API Key Management

### Required Environment Variables

For LLM integration to work:
```bash
# Anthropic (recommended for dazzle analyze-spec)
export ANTHROPIC_API_KEY=sk-ant-api03-...

# OR OpenAI (alternative)
export OPENAI_API_KEY=sk-...
```

### Where to Set Them

**Option 1: Shell Config** (recommended)
```bash
# Add to ~/.zshrc or ~/.bashrc:
export ANTHROPIC_API_KEY=sk-ant-...

# Then reload:
source ~/.zshrc
```

**Option 2: .env File**
```bash
# Create .env in project root:
echo 'ANTHROPIC_API_KEY=sk-ant-...' > .env

# Add to .gitignore:
echo '.env' >> .gitignore

# Load before running dazzle:
source .env
dazzle analyze-spec SPEC.md
```

**Option 3: VS Code Settings**
```json
// settings.json
{
  "terminal.integrated.env.osx": {
    "ANTHROPIC_API_KEY": "sk-ant-..."
  }
}
```

## Cost Estimation

### Token Usage for analyze-spec

Typical SPEC.md (like Urban Canopy example):
- Input tokens: ~2,000 (SPEC.md content)
- Output tokens: ~1,500 (generated DSL)
- **Cost**: ~$0.02 - $0.05 per SPEC (with Claude Sonnet)

For large specs (10+ entities):
- Input tokens: ~5,000
- Output tokens: ~3,000
- **Cost**: ~$0.10 - $0.20 per SPEC

### Cost Control

```bash
# Preview before generating:
dazzle analyze-spec SPEC.md --output-json | less
# (Shows what would be generated, no DSL output)

# Or use --estimate flag (if implemented):
dazzle analyze-spec SPEC.md --estimate-only
```

## Summary

### What Works NOW
✅ Claude can read SPEC.md and generate DSL via `dazzle analyze-spec`
✅ Claude can build and run the app automatically
✅ Context files guide Claude through the workflow
✅ No manual intervention needed after "Generate from SPEC"

### What Requires Future Work
⏳ VS Code command palette integration
⏳ Visual progress indicators
⏳ Interactive forms for customization
⏳ Direct API integration in extension

### Recommended UX (v0.1.0)
**Use Claude in VS Code** with `.claude/` context files
- Natural language workflow
- Fully automated
- Handles errors gracefully
- Works with current DAZZLE

---

**Last Updated**: 2025-11-23
**DAZZLE Version**: 0.1.0
**Integration Method**: Claude Code + LLM Context Files
