Resume after a Claude API glitch (rate limit, server error, dropped connection).

## When to invoke

The user typed `/glitch` because the previous agent run halted mid-task with an API
error like:
- "API Error: Server is temporarily limiting requests (not your usage limit) · Rate limited"
- 5xx from the API
- A dropped connection or message-stream cut-off

Your job is to **pick up where the previous run left off** without re-doing
already-completed work.

## Steps

1. **Read the last ~10 turns of context** to understand what was happening.
   Look for:
   - The most recent user instruction (what they asked you to do)
   - The last in-flight tool call or a clear "next action" you announced
   - Any half-finished commit, push, or test run

2. **Inspect concrete state** to see how far you actually got. Run these
   in parallel:
   - `git status --short` — uncommitted work?
   - `git log --oneline -5` — was the last commit completed?
   - If a long-running background task was active, check its
     output file under `/private/tmp/claude-501/.../tasks/` to see if it finished.

3. **Decide one of three resumption modes** based on state:

   a. **Clean worktree + last commit matches the announced action** → the
      previous run completed; just continue with the next step in the
      sequence (e.g. if you were in `/issues` mid-cycle, pick up the next
      issue; if you were in `/loop` mid-fire, fire the next iteration).

   b. **Uncommitted changes that match the in-flight action** → finish
      what was started: re-run the test gate that was about to run,
      then commit + push if everything's clean.

   c. **Ambiguous state** → tell the user in one or two sentences what
      you see and ask which way to resume. Don't guess if it's not
      obvious — re-doing or skipping a real step has cost.

4. **Don't re-issue commits or pushes** without verifying they didn't
   already happen. Check `git log` against the SHA you remember producing.

5. **Don't restart a long-running background task** without checking
   if the original is still running or already finished. Use `TaskList`.

## What this command is NOT

- Not a substitute for `/issues`, `/loop`, or any other workflow command.
  It's a recovery shim that hands control back to whatever was running.
- Not for normal "continue" prompts (those just need "continue" or "yes").
  Use `/glitch` only when an actual API error broke the conversation flow.

## Tone

Brief. The user knows the API blew up — don't dwell on it. Diagnose state,
state what you're picking up from, get back to the work.
