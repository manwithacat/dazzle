<!--
Thanks! One thing to know: this repo is a synced mirror of the Dazzle
monorepo (packages/hatchi-maxchi/ is the source of truth). Your PR is
reviewed HERE, then a maintainer ports the accepted change into the
monorepo with Co-authored-by credit to you; the next sync brings it back
and this PR is closed with a link to the landed commit. Details:
CONTRIBUTING.md.
-->

## What

<!-- The change, in a sentence or two. Name the Hyperpart(s) affected. -->

## Why

<!-- The problem or gap. Screenshots/GIFs for anything visual. -->

## Checks

- [ ] `python build.py && python -m pytest tests/` passes locally
- [ ] New/changed classes have CSS rules (incl. JS-assigned classNames)
- [ ] New `hx-*` affordances have declared `Exchange` contracts
- [ ] Interactive changes considered under touch (`pointer: coarse`)
