# Trial: manager_evaluation
*as You are Sarah, founder of a small B2B SaaS company with about 50 paying — 2026-07-29 05:59*

## Verdict

> (synthesized from recorded friction — agent ran out of steps)
> I only got a short look, but the one thing that stopped me cold was Manager Ops: scrolling the queue kicked off a storm of browser resource errors and failed background fetches that thrashed the page until it was only half-usable. That’s the exact screen I’d live in to spot urgency and reassign work for Alex—if it’s choking under light scroll, I can’t trust it for SLA oversight. I’m not running a two-week pilot on this yet; fix the Manager Ops polling/load thrash and I’d look again in 3 months.

*Run: 10 steps · 604s · 967,529 tokens · outcome=budget_exceeded*

## Friction observations (1)

### other

**Console storm of thousands of ERR_INSUFFICIENT_RESOURCES and htmx Failed to fet…**

> Console storm of thousands of ERR_INSUFFICIENT_RESOURCES and htmx Failed to fetch errors when scrolling Manager Ops — page partially usable but background polling/lazy loads thrash browser resources.

*severity:* medium · *where:* `http://localhost:3969/app/workspaces/manager_ops` · *ownership:* harness

```
Scroll on Manager Ops produced +3479 console errors: Failed to load resource: net::ERR_INSUFFICIENT_RESOURCES and repeated htmx:error Failed to fetch. Metrics and ticket links still visible despite storm.
```
