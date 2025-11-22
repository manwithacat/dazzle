# DAZZLE VS Code Extension - Troubleshooting Guide

## LSP Server Issues

### Error: "ModuleNotFoundError: No module named 'dazzle'"

**Problem**: The VS Code extension can't find the Python `dazzle` package.

**Symptoms**:
```
Error while finding module specification for 'dazzle.lsp' (ModuleNotFoundError: No module named 'dazzle')
Server process exited with code 1
The DAZZLE Language Server server crashed 5 times
```

**Solutions** (try in order):

#### Solution 1: Set Python Path in VS Code Settings

1. Open VS Code Settings (Cmd+, or Ctrl+,)
2. Search for "dazzle python"
3. Set **DAZZLE: Python Path** to your Python with dazzle installed

To find the correct Python path:
```bash
# Find your Python with dazzle installed
which python3

# Or if using pyenv
pyenv which python

# Or check where dazzle is installed
pip show dazzle | grep Location
```

Example paths:
- `/Users/yourname/.pyenv/shims/python`
- `/opt/homebrew/bin/python3`
- `/usr/local/bin/python3`

#### Solution 2: Install Dazzle in Development Mode

```bash
# Navigate to Dazzle project
cd /Volumes/SSD/Dazzle

# Install in editable mode
pip install -e .

# Or with LLM support
pip install -e ".[llm]"

# Verify installation
python -c "import dazzle; print(dazzle.__file__)"
```

#### Solution 3: Set Environment Variable

Add to your shell profile (~/.zshrc, ~/.bashrc, etc.):

```bash
export DAZZLE_PYTHON="/path/to/your/python3"
```

Then restart VS Code.

#### Solution 4: Use Python Extension's Interpreter

1. Install the official Python extension for VS Code
2. Select Python interpreter (Cmd+Shift+P → "Python: Select Interpreter")
3. Choose the Python environment where dazzle is installed
4. Reload VS Code window

---

## TypeScript Compilation Issues

### Extension Not Loading

**Problem**: Extension fails to activate.

**Symptoms**:
- Extension doesn't appear in Extensions panel
- Commands not available in Command Palette
- No syntax highlighting for .dsl files

**Solutions**:

#### Check Compilation

```bash
cd /Volumes/SSD/Dazzle/extensions/vscode

# Compile TypeScript
npm run compile

# Check for errors
echo $?  # Should be 0 for success
```

#### Check Output Files

```bash
# Verify compiled files exist
ls out/

# Should see:
# - extension.js
# - llmCommands.js
# - lspClient.js
# - commands.js
# - diagnostics.js
# - ui/analysisPanel.js
```

#### Clean Build

```bash
# Remove old build
rm -rf out/

# Reinstall dependencies
npm install

# Rebuild
npm run compile
```

---

## LLM Analysis Issues

### API Key Not Found

**Problem**: analyze-spec command fails with "No API key configured".

**Solutions**:

Set environment variable for your LLM provider:

```bash
# For Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# For OpenAI
export OPENAI_API_KEY="sk-..."
```

Add to your shell profile to persist.

### Analysis Dashboard Not Showing

**Problem**: Dashboard doesn't open after analysis.

**Troubleshooting**:

1. Check if analysis succeeded:
   - Look for success message
   - Check DAZZLE output channel

2. Check for JavaScript errors:
   - Open Developer Tools (Help → Toggle Developer Tools)
   - Look for errors in Console

3. Manually open dashboard:
   - Run analysis again
   - Choose "View Results Only" option

---

## Development Setup

### Recommended Setup for Contributing

```bash
# 1. Clone repository
git clone https://github.com/dazzle/dazzle.git
cd dazzle

# 2. Create Python virtual environment
python3 -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# 3. Install dazzle in development mode
pip install -e ".[dev,llm]"

# 4. Install VS Code extension dependencies
cd extensions/vscode
npm install

# 5. Compile TypeScript
npm run compile

# 6. Set Python path in VS Code
# Settings → DAZZLE: Python Path → /path/to/venv/bin/python

# 7. Test in Extension Development Host
# Press F5 in VS Code to launch extension development host
```

---

## Common Issues

### Issue: "DAZZLE CLI not found"

**Solution**: Install dazzle CLI or set `dazzle.cliPath` in VS Code settings:

```json
{
  "dazzle.cliPath": "/path/to/dazzle"
}
```

### Issue: "Validation failed"

**Causes**:
- DSL syntax errors
- Missing dazzle.toml
- Invalid backend configuration

**Check**:
```bash
# Validate manually
dazzle validate

# Check manifest
cat dazzle.toml
```

### Issue: Dashboard shows "No state machines detected"

**Causes**:
- Spec doesn't describe state workflows
- LLM couldn't identify state machines
- Analysis incomplete

**Tips**:
- Review your spec for state/workflow descriptions
- Try rephrasing: "The task has three states: todo, in progress, done"
- Check analysis output JSON for raw results

---

## Getting Help

1. **Check Logs**:
   - View → Output → Select "DAZZLE LSP" or "DAZZLE"
   - Look for detailed error messages

2. **Enable Verbose Logging**:
   ```json
   {
     "dazzle.trace.server": "verbose"
   }
   ```

3. **Report Issues**:
   - GitHub: https://github.com/dazzle/dazzle/issues
   - Include:
     - VS Code version
     - Extension version
     - Python version
     - Error messages from Output panel
     - Steps to reproduce

---

## Quick Reference

### VS Code Settings

```json
{
  // Python interpreter path
  "dazzle.pythonPath": "/Users/you/.pyenv/shims/python",

  // DAZZLE CLI path
  "dazzle.cliPath": "dazzle",

  // Auto-validate on save
  "dazzle.validateOnSave": true,

  // LLM provider
  "dazzle.llm.provider": "anthropic",

  // LLM model
  "dazzle.llm.model": "claude-3-5-sonnet-20241022",

  // Max cost per analysis (USD)
  "dazzle.llm.maxCostPerAnalysis": 1.0
}
```

### Environment Variables

```bash
# Python interpreter for LSP
export DAZZLE_PYTHON="/path/to/python"

# LLM API keys
export ANTHROPIC_API_KEY="sk-ant-..."
export OPENAI_API_KEY="sk-..."
```

---

**Last Updated**: November 22, 2025
