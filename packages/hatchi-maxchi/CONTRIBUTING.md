# Contributing

Thanks for your interest in HaTchi-MaXchi.

## The one thing to know first

**This repository is a synced mirror.** The source of truth is the
[Dazzle monorepo](https://github.com/manwithacat/dazzle), directory
`packages/hatchi-maxchi/` — every push there that touches the package is
subtree-synced here automatically. Nothing merges here directly: a commit
landed on this repo's `main` outside the sync would be overwritten by the
next one.

This is the standard read-only-mirror arrangement (the pattern used by
generated/exported repos across GitHub), with one difference worth
knowing: PRs here are still genuinely useful — they just land via a port.

## How a pull request works

1. Open the PR against this repo as normal. Keep it focused; include the
   *why*, and — for anything visual or interactive — a before/after
   screenshot or a short description of the behaviour change.
2. A maintainer reviews it here. Discussion, review comments, and CI all
   happen on your PR like any other project.
3. When accepted, a maintainer **ports the change into the monorepo**
   (where the full test harness runs: behaviour tests in two engines,
   WCAG/axe gates, visual baselines, contract + cohesion gates, and a
   12-app example fleet that consumes the components). The port commit
   carries `Co-authored-by:` credit to you, and the next sync brings it
   back here — at which point your PR is closed with a link to the
   landed commit.
4. If the port needs changes your PR didn't anticipate (usually a gate
   you couldn't run from here), the maintainer notes what changed and
   why on the PR before closing it.

If you'd rather skip the port round-trip and you're making sustained
contributions, ask for the change to be made in the monorepo directly —
`packages/hatchi-maxchi/` is an ordinary directory there.

## Issues

Open issues here. Bug reports about a component should name the
Hyperpart (its id from the [gallery](https://manwithacat.github.io/hatchi-maxchi/)),
the browser/OS, and — for interactive parts — whether the problem is in
the markup, the CSS, or the controller if you can tell. Feature requests
are welcome; the bar for new Hyperparts is documented in the README
("Add a Hyperpart").

## Running the gates locally

```bash
pip install pytest playwright pillow && playwright install chromium webkit
python build.py && python -m pytest tests/
```

The gates you're most likely to trip, and what they mean, are described
in the README's Development section. Two easy ones to remember:

- every class your markup uses needs a CSS rule (or an explicit
  `SEMANTIC_ONLY` entry with a comment) — including classes a controller
  assigns from JS;
- every `hx-*` request affordance needs a declared `Exchange` contract,
  and every declared contract needs a real affordance.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
Be kind; assume good faith.
