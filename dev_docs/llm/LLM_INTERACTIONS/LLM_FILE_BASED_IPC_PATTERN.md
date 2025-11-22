# File-Based IPC Pattern for CLI Tool Coordination
## Economic Rationale & Design Best Practices

---

## Economic Reality: Subscriptions Beat APIs for Heavy Use

### Token Pricing Comparison

**API Pricing (Pay-per-token)**
```
Anthropic Claude Sonnet:
  Input:  $3.00 / 1M tokens
  Output: $15.00 / 1M tokens

Typical spec analysis:
  Input:  ~12K tokens (spec + prompt)
  Output: ~8K tokens (analysis JSON)
  Cost:   $0.156 per analysis

Daily usage (DAZZLE developer iterating):
  10 analyses/day × $0.156 = $1.56/day
  Month: $46.80
```

**Subscription Pricing (Unlimited)**
```
Claude Pro: $20/month (unlimited)
ChatGPT Plus: $20/month (unlimited)
Cursor: $20/month (unlimited with Claude/GPT-4)

Same daily usage:
  10 analyses/day × $0 = $0/day
  Month: $20 (fixed)

Break-even: ~130 analyses/month = 4.3/day
```

### Why This Matters for DAZZLE

**Typical DAZZLE developer workflow:**
```
Day 1: Initial spec analysis (1x)
Day 2: Refine spec, re-analyze (3x)
Day 3: Add features, re-analyze (4x)
Day 4: Client feedback, re-analyze (2x)
...
Week 1 total: 15-20 analyses

API cost: $3.00+
Subscription cost: $20/month (covers unlimited iterations)
```

**Conclusion**: Heavy DAZZLE users save money with subscriptions → CLI tools make sense

---

## Why File-Based IPC is Optimal

### Comparison of IPC Methods

| Method | Complexity | Debuggability | Portability | Human-Inspectable |
|--------|-----------|---------------|-------------|-------------------|
| **Files** | Low | Excellent | Universal | Yes ✓ |
| Stdin/Stdout | Low | Poor | Good | No |
| Named Pipes | Medium | Poor | Unix-only | No |
| Sockets | High | Poor | Good | No |
| HTTP Server | High | Medium | Good | Partially |
| RPC (gRPC) | Very High | Poor | Good | No |

**Files win on:**
- ✓ Simplicity (read/write, that's it)
- ✓ Debuggability (just cat the files)
- ✓ Universal (works everywhere)
- ✓ Human-inspectable (can manually edit)
- ✓ No dependencies (just filesystem)
- ✓ Stateful (files persist for debugging)

### The Unix Philosophy

> "Write programs that do one thing well. Use text streams as the universal interface."

**Modern interpretation:**
```
Files ARE the universal interface.

Every tool can:
  - Read files
  - Write files
  - Follow a schema
```

**DAZZLE + Claude Code example:**
```
DAZZLE says: "Here's the spec (file), analyze it (instructions file),
              write output here (location)"

Claude Code says: "Got it. Reading... Analyzing... Writing..."

DAZZLE says: "Thanks! Reading your output..."
```

**No API needed. No complex protocol. Just files.**

---

## File-Based IPC Design Pattern

### Core Pattern

```
Producer (DAZZLE)              Consumer (LLM Tool)
       ↓                              ↓
   [Write files]                 [Read files]
       ↓                              ↓
   Workspace Dir  ←─────────────→  Process
       ↓                              ↓
   [Wait/Poll]                  [Write output]
       ↓                              ↓
   [Read output]                 [Exit/Signal]
```

### Directory Contract

```
workspace/
├── input/                    # Producer writes, Consumer reads
│   ├── manifest.json         # What needs to be done
│   ├── data.txt              # Input data
│   └── schema.json           # Expected output format
├── output/                   # Consumer writes, Producer reads
│   ├── result.json           # Output data
│   └── metadata.json         # Execution info (timing, errors)
└── shared/                   # Both can read/write
    ├── status.txt            # Current status
    └── logs.txt              # Streaming logs
```

### Manifest Format

**`input/manifest.json`**
```json
{
  "task": "analyze-spec",
  "version": "1.0",
  "created_at": "2025-11-21T23:30:00Z",

  "inputs": {
    "spec": "input/SPEC.md",
    "instructions": "input/instructions.md",
    "schema": "input/schema.json"
  },

  "outputs": {
    "result": "output/analysis.json",
    "required": true,
    "schema": "input/schema.json"
  },

  "constraints": {
    "timeout_seconds": 300,
    "max_retries": 1
  }
}
```

### Status Signaling

**`shared/status.txt`** (simple status file)
```
PENDING    # Initial state
RUNNING    # Consumer started
COMPLETE   # Success
FAILED     # Error occurred
```

**Or use lock files:**
```
workspace/
├── .lock          # Consumer writes this when starting
├── .done          # Consumer writes this when complete
└── .error         # Consumer writes this on failure
```

**DAZZLE polling logic:**
```python
def wait_for_completion(workspace: Path, timeout: int = 300):
    """Wait for consumer to complete, polling status."""
    start_time = time.time()

    while time.time() - start_time < timeout:
        if (workspace / ".done").exists():
            return "complete"
        elif (workspace / ".error").exists():
            return "failed"
        elif not (workspace / ".lock").exists():
            return "not_started"

        time.sleep(1)  # Poll every second

    return "timeout"
```

### Error Handling

**`output/metadata.json`** (consumer writes on completion)
```json
{
  "status": "complete",
  "started_at": "2025-11-21T23:30:05Z",
  "completed_at": "2025-11-21T23:30:47Z",
  "duration_seconds": 42,

  "execution": {
    "tool": "claude-code",
    "version": "1.2.3",
    "model": "claude-3-5-sonnet-20241022"
  },

  "result": {
    "output_file": "output/analysis.json",
    "size_bytes": 12458,
    "valid": true
  },

  "errors": []
}
```

**Or on error:**
```json
{
  "status": "failed",
  "started_at": "2025-11-21T23:30:05Z",
  "failed_at": "2025-11-21T23:30:12Z",

  "errors": [
    {
      "type": "validation_error",
      "message": "Output JSON does not match schema",
      "details": "Missing required field: 'state_machines'"
    }
  ]
}
```

---

## Advanced Patterns

### 1. Streaming Progress

**For long-running tasks**, consumer can write progress updates:

**`shared/progress.txt`**
```
[2025-11-21 23:30:05] Starting analysis...
[2025-11-21 23:30:08] Reading spec (12KB)...
[2025-11-21 23:30:15] Extracting state machines...
[2025-11-21 23:30:28] Found 1 state machine (Ticket.status)
[2025-11-21 23:30:32] Analyzing CRUD operations...
[2025-11-21 23:30:45] Writing output...
[2025-11-21 23:30:47] Complete!
```

**DAZZLE can tail this file:**
```python
def show_progress(workspace: Path):
    """Tail the progress file."""
    progress_file = workspace / "shared" / "progress.txt"

    if not progress_file.exists():
        return

    # Tail -f equivalent
    with open(progress_file) as f:
        f.seek(0, 2)  # Seek to end
        while True:
            line = f.readline()
            if line:
                print(f"  {line.strip()}")
            else:
                time.sleep(0.1)

            if (workspace / ".done").exists():
                break
```

### 2. Incremental Results

**For streaming output**, consumer can write partial results:

```
output/
├── analysis.partial.json      # Updated as work progresses
└── analysis.final.json        # Written on completion
```

**DAZZLE can show partial results:**
```python
def watch_partial_results(workspace: Path):
    """Display partial results as they arrive."""
    partial_file = workspace / "output" / "analysis.partial.json"

    last_modified = 0
    while not (workspace / ".done").exists():
        if partial_file.exists():
            current_modified = partial_file.stat().st_mtime
            if current_modified > last_modified:
                # File updated, show new results
                with open(partial_file) as f:
                    data = json.load(f)
                display_partial_analysis(data)
                last_modified = current_modified

        time.sleep(2)
```

### 3. Bidirectional Communication

**For interactive workflows**, both can write to shared space:

```
shared/
├── questions.json             # Consumer asks, Producer answers
└── answers.json              # Producer responds
```

**Consumer (Claude Code) writes:**
```json
{
  "questions": [
    {
      "id": "q1",
      "text": "Should users be able to edit their own profiles?",
      "options": ["Yes", "No", "Admin only"]
    }
  ]
}
```

**Producer (DAZZLE) responds:**
```json
{
  "answers": [
    {
      "id": "q1",
      "answer": "Yes"
    }
  ]
}
```

**Consumer continues with answers.**

### 4. Multi-Stage Pipelines

**Chain multiple tools:**

```
Stage 1: spec-analyzer (Claude Code)
  input/SPEC.md → output/analysis.json

Stage 2: dsl-generator (GPT-4)
  input/analysis.json → output/app.dsl

Stage 3: code-generator (DAZZLE)
  input/app.dsl → output/build/
```

**Each stage is a separate workspace:**
```
.dazzle/
├── stage-1-analysis/
│   ├── input/SPEC.md
│   └── output/analysis.json
├── stage-2-dsl/
│   ├── input/analysis.json (symlink to stage-1)
│   └── output/app.dsl
└── stage-3-build/
    ├── input/app.dsl (symlink to stage-2)
    └── output/build/
```

---

## Best Practices

### 1. Use JSON for Structured Data

**Not this:**
```
output/result.txt:
  Found state machine: Ticket.status
  States: open, in_progress, resolved, closed
  Transitions: 7
```

**This:**
```json
{
  "state_machines": [
    {
      "entity": "Ticket",
      "field": "status",
      "states": ["open", "in_progress", "resolved", "closed"],
      "transition_count": 7
    }
  ]
}
```

**Why:** Machine-readable, schema-validatable, less brittle

### 2. Include Schema with Data

**Always provide schema:**
```
input/
├── data.json           # The data
└── data.schema.json    # How to interpret it
```

**Consumer can validate:**
```python
import jsonschema

with open("input/data.schema.json") as f:
    schema = json.load(f)

with open("input/data.json") as f:
    data = json.load(f)

jsonschema.validate(data, schema)  # Raises if invalid
```

### 3. Use Timestamps for Ordering

**When multiple files might be written:**
```
output/
├── analysis_20251121_233005.json
├── analysis_20251121_233142.json  ← Latest
└── analysis_20251121_233287.json
```

**Or use manifest:**
```json
{
  "files": [
    {
      "name": "analysis.json",
      "created_at": "2025-11-21T23:30:05Z",
      "version": 1
    }
  ]
}
```

### 4. Clean Up After Success

**Don't leave garbage:**
```python
def cleanup_workspace(workspace: Path, keep_output: bool = True):
    """Clean up workspace after successful completion."""

    # Always keep output
    output_dir = workspace / "output"
    output_files = list(output_dir.glob("*"))

    if keep_output:
        # Move to results directory
        results_dir = Path(".dazzle/results")
        results_dir.mkdir(exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")
        result_file = results_dir / f"analysis_{timestamp}.json"
        shutil.copy(output_dir / "analysis.json", result_file)

    # Remove workspace
    shutil.rmtree(workspace)
```

### 5. Handle Concurrent Access

**If multiple DAZZLE instances might run:**
```python
import fcntl

def create_workspace(base_dir: Path) -> Path:
    """Create workspace with unique name."""

    # Use PID for uniqueness
    pid = os.getpid()
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    workspace = base_dir / f"workspace_{timestamp}_{pid}"

    workspace.mkdir(parents=True, exist_ok=False)
    return workspace

def acquire_lock(workspace: Path) -> int:
    """Acquire exclusive lock on workspace."""
    lock_file = workspace / ".lock"
    fd = open(lock_file, 'w')

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd.write(str(os.getpid()))
        fd.flush()
        return fd
    except IOError:
        raise RuntimeError(f"Workspace {workspace} is locked")
```

---

## Security Considerations

### 1. Validate Input

**Consumer should validate all inputs:**
```python
def validate_workspace(workspace: Path):
    """Validate workspace structure before processing."""

    required_files = [
        "input/manifest.json",
        "input/SPEC.md",
        "input/schema.json"
    ]

    for file_path in required_files:
        full_path = workspace / file_path
        if not full_path.exists():
            raise ValueError(f"Missing required file: {file_path}")

        # Check file size (prevent DoS)
        if full_path.stat().st_size > 10 * 1024 * 1024:  # 10MB
            raise ValueError(f"File too large: {file_path}")

    # Validate JSON
    with open(workspace / "input/manifest.json") as f:
        manifest = json.load(f)
        # Validate manifest schema
```

### 2. Sandbox Workspace

**Keep workspace isolated:**
```python
def create_sandboxed_workspace(base_dir: Path) -> Path:
    """Create workspace with restricted permissions."""

    workspace = create_workspace(base_dir)

    # Set restrictive permissions (owner only)
    os.chmod(workspace, 0o700)

    # Create directories
    for subdir in ["input", "output", "shared"]:
        (workspace / subdir).mkdir()
        os.chmod(workspace / subdir, 0o700)

    return workspace
```

### 3. Prevent Path Traversal

**Validate file paths:**
```python
def safe_path(workspace: Path, relative_path: str) -> Path:
    """Ensure path stays within workspace."""

    full_path = (workspace / relative_path).resolve()

    # Check if path is within workspace
    if not str(full_path).startswith(str(workspace.resolve())):
        raise ValueError(f"Path traversal detected: {relative_path}")

    return full_path
```

### 4. Timeout Protection

**Prevent runaway consumers:**
```python
def run_with_timeout(consumer_func, timeout: int = 300):
    """Run consumer with timeout."""

    import signal

    def timeout_handler(signum, frame):
        raise TimeoutError(f"Consumer exceeded timeout ({timeout}s)")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)

    try:
        result = consumer_func()
        signal.alarm(0)  # Cancel alarm
        return result
    except TimeoutError:
        raise
```

---

## DAZZLE Implementation

### Workspace Manager

**File: `dazzle/llm/workspace.py`**

```python
from pathlib import Path
import json
import time
import shutil
from typing import Optional, Dict, Any

class LLMWorkspace:
    """Manages file-based IPC workspace for LLM tools."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path.home() / ".dazzle" / "llm_handoff"
        self.workspace: Optional[Path] = None

    def create(self, task_name: str = "analysis") -> Path:
        """Create new workspace."""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        pid = os.getpid()

        self.workspace = self.base_dir / f"{task_name}_{timestamp}_{pid}"
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Create structure
        (self.workspace / "input").mkdir()
        (self.workspace / "output").mkdir()
        (self.workspace / "shared").mkdir()

        return self.workspace

    def write_manifest(self, task: str, inputs: Dict[str, str],
                       outputs: Dict[str, str], **kwargs):
        """Write task manifest."""
        manifest = {
            "task": task,
            "version": "1.0",
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "inputs": inputs,
            "outputs": outputs,
            **kwargs
        }

        manifest_file = self.workspace / "input" / "manifest.json"
        with open(manifest_file, 'w') as f:
            json.dump(manifest, f, indent=2)

    def write_input(self, name: str, content: str):
        """Write input file."""
        input_file = self.workspace / "input" / name
        input_file.write_text(content)

    def read_output(self, name: str) -> str:
        """Read output file."""
        output_file = self.workspace / "output" / name
        return output_file.read_text()

    def wait_for_completion(self, timeout: int = 300) -> str:
        """Wait for consumer to complete."""
        start = time.time()

        while time.time() - start < timeout:
            if (self.workspace / ".done").exists():
                return "complete"
            elif (self.workspace / ".error").exists():
                return "failed"

            time.sleep(1)

        return "timeout"

    def cleanup(self, keep_output: bool = True):
        """Clean up workspace."""
        if keep_output:
            # Archive output
            results_dir = self.base_dir.parent / "results"
            results_dir.mkdir(exist_ok=True)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            archive_name = f"result_{timestamp}.json"

            output_file = self.workspace / "output" / "analysis.json"
            if output_file.exists():
                shutil.copy(output_file, results_dir / archive_name)

        # Remove workspace
        shutil.rmtree(self.workspace)
```

### Usage in DAZZLE

```python
def analyze_spec_with_cli_tool(spec_content: str, tool: str):
    """Analyze spec using CLI tool via file-based IPC."""

    # Create workspace
    ws = LLMWorkspace()
    workspace = ws.create("spec_analysis")

    print(f"📁 Workspace: {workspace}")

    # Write inputs
    ws.write_manifest(
        task="analyze-spec",
        inputs={
            "spec": "input/SPEC.md",
            "instructions": "input/instructions.md",
            "schema": "input/schema.json"
        },
        outputs={
            "analysis": "output/analysis.json",
            "required": True
        },
        constraints={
            "timeout_seconds": 300
        }
    )

    ws.write_input("SPEC.md", spec_content)
    ws.write_input("instructions.md", generate_instructions())
    ws.write_input("schema.json", json.dumps(get_schema(), indent=2))

    # Invoke tool (platform-specific)
    if tool == "claude-code":
        # Open in VS Code with Claude
        subprocess.run(f"code {workspace}", shell=True)

        print("\n📋 Please use Claude Code to:")
        print("  1. Read input/instructions.md")
        print("  2. Analyze input/SPEC.md")
        print("  3. Write output/analysis.json")
        print("\nPress Enter when complete...")
        input()

    elif tool == "aider":
        # Run aider in workspace
        cmd = f"""
        cd {workspace} && aider --yes --message \
        "Read input/instructions.md and analyze input/SPEC.md. \
        Write complete analysis to output/analysis.json."
        """
        subprocess.run(cmd, shell=True, timeout=300)

    # Check status
    status = ws.wait_for_completion(timeout=300)

    if status == "complete":
        # Read output
        analysis_json = ws.read_output("analysis.json")
        analysis = json.loads(analysis_json)

        # Validate
        validate_analysis(analysis)

        # Cleanup
        ws.cleanup(keep_output=True)

        return analysis

    elif status == "failed":
        error_file = workspace / ".error"
        error_msg = error_file.read_text() if error_file.exists() else "Unknown error"
        raise RuntimeError(f"Analysis failed: {error_msg}")

    else:
        raise TimeoutError(f"Analysis timed out after 300s")
```

---

## Conclusion

**File-based IPC is the right choice for DAZZLE because:**

1. **Economic**: Enables subscription-based LLM usage (cheaper for heavy users)
2. **Simple**: Just read/write files (no complex protocols)
3. **Universal**: Works with any tool (Claude Code, Cursor, Aider, custom)
4. **Debuggable**: Can inspect/edit files manually
5. **Flexible**: Supports streaming, bidirectional communication, pipelines
6. **Reliable**: Filesystem is stable, well-understood

**The pattern:**
- Producer prepares workspace with inputs
- Consumer processes and writes outputs
- Signaling via lock files (`.lock`, `.done`, `.error`)
- Structured data via JSON
- Schema validation for safety

**This is IPC done right** - simple, robust, and subscription-friendly.
