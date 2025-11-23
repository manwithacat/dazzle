# Claude Integration - Quick Start Guide

## What Was Built

A seamless, **TOS-compliant** integration between DAZZLE and Claude in VS Code that:
- ✅ Detects SPEC.md automatically
- ✅ Detects if Claude extension is installed
- ✅ Provides one-click "Copy Prompt" button
- ✅ User pastes in Claude → Full app generated automatically
- ✅ **No manual steps** (just paste!)

## Installation

```bash
# 1. Install the updated extension
code --install-extension /Volumes/SSD/Dazzle/extensions/vscode/dazzle-dsl-0.4.0.vsix

# 2. Reload VS Code
# Cmd+Shift+P → "Reload Window"
```

## Test It NOW

### Test with Your Urban Canopy Project

```bash
# 1. Open your test project
code /Volumes/SSD/test

# 2. Wait 3 seconds after opening

# 3. You should see:
#    [Notification] "💡 SPEC.md detected! Generate DAZZLE app with Claude?"
#    [Status Bar]   "💡 Ask Claude to Generate App"

# 4. Click "Copy Prompt to Clipboard"

# 5. Open Claude (Cmd+Shift+I or click chat icon)

# 6. Paste (Cmd+V)

# 7. Claude automatically:
#    - Reads your SPEC.md
#    - Runs: dazzle analyze-spec SPEC.md --no-interactive --generate-dsl
#    - Runs: dazzle validate
#    - Runs: dazzle build --stack micro
#    - Shows you how to run the app

# 8. Done! Your Urban Canopy app is ready.
```

## Expected Results

After pasting in Claude, you should see:

```
Claude: "I'll help you transform your SPEC.md into a working application.

Let me read the SPEC.md file first..."

[Reads SPEC.md]

Claude: "I see this is an Urban Canopy tree monitoring system with 4 main entities:
- Tree (species, location, condition)
- Observation (moisture, leaf condition, insects)
- MaintenanceTask (watering, mulching, pruning)
- Volunteer (name, skills, active status)

Now I'll generate the DSL using DAZZLE's LLM integration..."

[Executes: dazzle analyze-spec SPEC.md --no-interactive --generate-dsl]

Claude: "✓ DSL generated at dsl/generated.dsl

Let me validate it..."

[Executes: dazzle validate]

Claude: "✓ Validation passed

Now building the application..."

[Executes: dazzle build --stack micro]

Claude: "✓ Application built successfully!

Your Urban Canopy app is ready. To run it:

cd build/urban_canopy
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver

Open http://localhost:8000 to see your tree monitoring system!"
```

## What the User Experience Looks Like

### Before (Manual)
```
1. User: "How do I generate an app from SPEC.md?"
2. AI: "Run dazzle analyze-spec"
3. User: Runs command
4. AI: "Now run dazzle validate"
5. User: Runs command
6. AI: "Now run dazzle build"
7. User: Runs command
8. Total: ~5 minutes, multiple steps
```

### After (Automated with This Integration)
```
1. Notification: "💡 Generate app with Claude?"
2. User: Clicks "Copy Prompt"
3. User: Pastes in Claude
4. Claude: Executes all steps automatically
5. Total: ~2 minutes, ONE paste
```

## Customization

### Disable Auto-Detection

If you don't want notifications:

```json
// settings.json
{
  "dazzle.claude.autoDetect": false,
  "dazzle.claude.showNotifications": false
}
```

### Change Prompt Template

Edit `.claude/WORKFLOW_SPEC_TO_APP.md` in your project to customize the workflow.

## Troubleshooting

### "I don't see the notification"

**Check**:
1. Is SPEC.md in the project root?
   ```bash
   ls /Volumes/SSD/test/SPEC.md
   ```
2. Is the dsl/ directory empty or just template?
   ```bash
   cat /Volumes/SSD/test/dsl/app.dsl
   ```
3. Did you wait 3 seconds after opening?

**Fix**: Click the status bar item manually ("💡 Ask Claude to Generate App")

### "Claude extension not detected"

**Check**:
```bash
code --list-extensions | grep claude
```

**Expected**: `anthropic.claude` or similar

**Fix**:
```bash
# Search for "Claude" in VS Code Marketplace
# Or install directly:
code --install-extension anthropic.claude
```

### "Prompt doesn't work"

**Check**: You're using Claude's VS Code extension (not Claude desktop app)

**Note**: Claude VS Code extension uses your logged-in subscription - no API key needed!

## Architecture

```
VS Code Opens Project
       ↓
DAZZLE Extension Activates
       ↓
Detects: SPEC.md exists + DSL empty
       ↓
Shows: [💡 Generate app with Claude?]
       ↓
User Clicks: "Copy Prompt to Clipboard"
       ↓
Prompt Copied (pre-crafted workflow instructions)
       ↓
User Opens: Claude Chat (Cmd+Shift+I)
       ↓
User Pastes: Cmd+V
       ↓
Claude Reads: .claude/PROJECT_CONTEXT.md
Claude Reads: .claude/WORKFLOW_SPEC_TO_APP.md
Claude Reads: SPEC.md
       ↓
Claude Executes:
   1. dazzle analyze-spec SPEC.md --no-interactive --generate-dsl
   2. dazzle validate
   3. dazzle build --stack micro
       ↓
App Generated & Ready
```

## Why This Approach Works

### No TOS Violations
- ✅ User explicitly clicks "Copy Prompt"
- ✅ User explicitly pastes in Claude
- ✅ No automation of chat inputs
- ✅ Claude extension uses user's subscription (no API keys)

### Better Than Direct Integration
- ✅ Claude handles errors naturally
- ✅ Claude can ask clarifying questions
- ✅ Claude provides explanations
- ✅ Free with Claude subscription
- ✅ No API key management

### Minimal Friction
- ✅ One notification
- ✅ One click (Copy Prompt)
- ✅ One paste
- ✅ Done!

## Next Steps

1. **Test Now**: Open `/Volumes/SSD/test` in VS Code
2. **Watch the Magic**: Claude generates your Urban Canopy app
3. **Customize**: Edit `.claude/WORKFLOW_SPEC_TO_APP.md` for your needs
4. **Share**: This UX works for any DAZZLE project with SPEC.md

## Feedback

If it works: Amazing! You have the ideal VS Code + Claude + DAZZLE UX.

If it doesn't: Check the troubleshooting section or open an issue with:
- VS Code version
- Claude extension version
- Console output (Help → Toggle Developer Tools → Console)

---

**Built**: 2025-11-23
**Version**: DAZZLE v0.4.0
**Status**: Ready for Testing 🎉
