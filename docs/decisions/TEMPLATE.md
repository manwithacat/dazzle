# DD-NNN: &lt;short title&gt;

```yaml
# Machine-readable header (keep keys stable — greppable by agents)
id: DD-NNN
status: PARKED          # PARKED | FORCED | DONE | SUPERSEDED
issues: []              # e.g. [1621, 1622]
adrs: []                # related ADRs
decided: YYYY-MM-DD
decided_at_sha: null    # optional tip SHA when parked
parent: null            # umbrella issue or prior DD
```

## One-line intent

&lt;What we decided *not* to build yet, and why that is intentional.&gt;

## Plan (what we already concluded)

&lt;The design that should not be rediscovered from scratch months later.
Include counter-priors: what we will **not** do even when forced.&gt;

## Reopen when (consumer force)

Concrete, checkable signals — not vibes:

1. **Named consumer** — app or product module: `…`
2. **Evidence of dual-lock / host workaround** — path or issue: `…`
3. **Acceptance that unblocks** — e.g. “poly_ref without host dual-lock on Comment”

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan below; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

&lt;Substrate, ADRs, prove commands that already hold.&gt;

## Explicitly out of scope until force

&lt;…&gt;

## Trail

| Date | Event |
|------|--------|
| YYYY-MM-DD | Parked (this DD) |
