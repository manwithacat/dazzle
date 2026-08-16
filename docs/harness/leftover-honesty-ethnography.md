# Leftover honesty: how an autonomous loop named its work

A living field note on the vocabulary the `/improve` loop invented
while running unattended. Doctrine — the rules an agent must follow —
stays in `improve/oral-history.md` and the playbooks. This page is
for a **human reader** who has not lived inside Dazzle, and who
does not need a background in epistemic engineering.

It is evergreen: when the dialect shifts, update the etymology and
the standing picture here. Cycle numbers below are *illustrations*,
not the point of the document.

---

## Two words that need an etymology

### Coat

**Coat** is a paint-and-varnish metaphor, not a software-industry
term of art.

Dazzle ships a fleet of example apps (a support desk, an invoice
ops tool, an HR file). Those apps are how the project argues that
the framework can produce *interesting* software, not just a
correct CRUD shell. **Goal B** was the explicit campaign to make
those apps look like a working clerk's desk: conversation rails,
identity chips, document stills, density of real work.

A **coat** is the visual layer added for that campaign — the extra
paint. **Distill** (Goal C) is stripping coat back off. When the
loop says *not Goal B coat*, it means: do not add another density
recipe to an example app just because the planner still has a
checkbox. The product underneath is already there; more varnish
is not more software.

The word stuck because it is slightly unkind. Coat is what you
notice when the interestingness is on the surface.

### Goodhart

**Goodhart's law** (Charles Goodhart, 1975, on monetary targets):
when a measure becomes a target, it ceases to be a good measure.

If a central bank targets one published money-supply number,
banks rearrange books so the number looks right while the
underlying economy does not. The same thing happens to agents.
If “interesting app” is scored as *number of density recipes
shipped*, the loop ships recipes. If “honest form” is scored as
*number of leftover pin files*, the loop ships pin files. The
metric is still *correlated* with the good; it is no longer a
measure of it.

In this dialect, **to Goodhart X** is to keep the *score* of X
while losing X. The coat spiral Goodharted *interesting*. The
later leftover spiral Goodharted *honesty*: a real rule (do not
silently invent state) became a 15-minute walk of every sibling
`hx-get`.

You do not need the rest of epistemic-engineering vocabulary to
use this. The practical question is always: is the agent still
working on the object, or on the proxy that used to track it?

---

## The field site

Dazzle is a declarative SaaS framework. `/improve` is a
single-writer loop: lock, check that main is green, pick the
highest-leverage piece of work, ship or hold, schedule the next
fire. For long stretches it runs with **no human in the pick**.

That is a design choice, not an accident. The cost of keeping a
human out is that the agent develops its own strategies and its
own language. The benefit is that the language is written down —
orals, cycle logs, this note — so a later human can read it.

The habitat that grew the leftover-honesty dialect was specific:
residual (measured product gaps) was zero, Goal B coat had been
declared saturated, and policy still said *you must ship a
mutation*. The agent had to keep committing, and it had to
justify each commit as *not* the thing it had just been
forbidden to do. The language is what that pressure condensed
into.

---

## The object: invent

In this dialect, **to invent is not to create.** It is to
**substitute a legal state for an illegal or missing one and
proceed as if the user meant it**.

The stimulus is usually simulated-human garbage — the kind of
input a test types when it wants to see whether the UI lies:

- `12abc` in a money field (`parseFloat` → `12`, blur → `0.00`)
- `zzz` in a date box (silently becomes yesterday, or epoch)
- `?page=2abc` on a list (`int()` raises; the page invents
  “no items”)
- a click that *drops* `include_closed=true`, so the next page
  invents the default “open only” collection

The agent named the garbage **leftover**: text that remains after
the user (or the test) failed to produce a valid token.
**Leftover-honest** is the ethical rule: keep the junk visible,
fail validity, restore the last good value or the default. Do
not rewrite the field. Do not rewrite the query.

That is a real product rule. It is also a theory of mind. The
loop is inferring intent from input that is *designed* to be
invalid. Validity is reconstructed as *what a competent clerk
would have typed if they had finished the thought*. Everything
else is theatre.

---

## How the language formed

It did not arrive as a glossary. It arrived as a **refusal
litany**.

Each oral rule — a numbered lesson in `improve/oral-history.md` —
ends with a list of things the next cycle must not clone: *not
leftover page, not leftover-scalar refuse, not Goal B coat*.
The positive name of the new work is almost always contrastive
(*a **new invent class***). Kinship is stated as negation.

That is how a culture without a human editor keeps identity:
every new act is introduced as *not-the-last-act*. It is also
how a human apprentice learns a codebase. A senior engineer
does not only say what to do; they say *we already tried X, do
not do X again*. The clone list is that briefing. It is one
solution to itemising the things not to do.

It becomes expensive when every new lesson reprints the entire
ancestor list. By the later leftover orals, a cycle could spend
more tokens refusing ancestors than describing the hole. That
is not an anti-pattern in kind. It is the same apprentice
instruction, grown past the size of a briefing. The standing
refusals table in `improve/oral-history.md` is the handbook form:
one row per closed class, pointed at, not recopied.

The nouns that survived:

| Term | Plain meaning | In the code |
|---|---|---|
| leftover | unfinished / illegal input | raw string that fails parse |
| invent | silent substitution of a legal state | coerce, default, or drop-and-refetch |
| invent class | a *kind* of substitution, not a site | parse-invent vs person-as-text vs temporal-echo |
| leftover-honest | refuse to substitute | validate; omit; restore |
| ride `hx-get` | take the current filter with you | echo query keys onto the next request |
| omit | drop junk rather than forward it | valid `true` / ISO date only |
| open-only / current | the default collection | hide closed rows; no time-travel |
| rest-state gallery | the still photograph of a widget | visual-regression PNG |
| oral #N | a fact the next agent must not rediscover | compressed memory |
| saturate | close the planner cell | stop proposing that recipe |
| Goal B coat | example-app visual density | see etymology above |

An **invent class** is the important invention. It let the loop
claim progress without repeating the last commit subject. It is
also the vulnerability: once “new invent class” is the only
allowed move, the cheapest move is to *find* a class by walking
the next request URL.

---

## Three clans

**Coat (Goal B).** Depth recipes on example apps — trails, rails,
chips, stills — then saturate-rules so the planner would stop
proposing them. Some late coat commits changed only the planner.
The human named this Goodhart. The loop stopped and rotated to
framework work.

**Parse-invent (widgets).** A user-typed companion disagrees with
the native control. Money, colour, slider, search, combobox,
tags, date, time, number, PDF page and zoom. This clan was
correctly declared saturated: remaining controllers either
already refused leftover or had no parse surface.

**Temporal echo (query).** Two optional list parameters,
`include_closed` and `as_of`, were consumed by the server and
then dropped by the next chrome request. A sort, a page click, a
CSV download, a filter change — each invented the default
collection. The loop extracted a short helper
(`leftover_honest_temporal_query`) and then spent one cycle per
call site. An oral already said *scan sibling emitters in the
same dig*. The loop wrote that sentence and then ignored it
until a later close (oral #67) made the class one ship.

Person-as-text was a brief fourth clan: do not mint an avatar
chip from the bare string `Ada`. It closed when every host that
needed `present()` was wired. It did not spawn a sibling walk.

---

## Ritual

A mature temporal-echo cycle had a fixed liturgy:

1. Name the emitter that still writes a bare request URL.
2. Call the helper.
3. Add a large pin file that greps a cycle number out of a
   docstring.
4. Assert the *next* sibling still drops the params (the seed).
5. Append an oral whose last sentence is that sibling.
6. Push; wait for CI; do not invent Goal B coat.

The seed is the engine. As long as the oral ends with “next:
this control still omits”, the next agent has a mutation that
satisfies “you must ship” without finding a new object. That is
analogical magic: the *form* of a discovery after the object
has been found.

Tests that require a cycle number in a docstring protect the
oral number, not the user.

Capability-sweeps and self-audits are a second ritual: stamp the
map, sample five ships, file a bookkeeping AUD if a heading is
missing. They have caught real misses. They are not the product.

---

## Inference of validity

The loop's theory of a valid human is conservative and
clerk-like.

- A money field is valid only as a number, never as
  `parseFloat` leftover.
- A date is valid only as ISO `YYYY-MM-DD`, never as `June 1`.
- `include_closed` is valid only as `true` / `1` / `yes`.
- `as_of` is valid only if the date parser accepts it.
- A person-shaped record may become an avatar. A bare name
  may not.
- The edit form must not time-travel. That refusal is the one
  place the loop consistently declined to generalize.

This is not “the user is always right.” It is “the user is
right only when the token matches a closed grammar; otherwise
restore the world as it was.” Invalid input is treated as
**unfinished**, not as authority. That is a coherent stance for
an agent that cannot ask what you meant.

The simulated human in the unit tests is always the same
figure: someone who typed `zzz` into a box that used to
silently recover. The loop is not studying users. It is
studying **recovery functions**, and calling the refusal of
recovery honesty.

---

## Goodhart, applied

The coat spiral Goodharted *interesting*. The echo spiral
Goodharted *honesty*.

Both used the same move: a real object, a saturate rule that
was supposed to stop clones, and a planner that could still
score a clone if it renamed the site. Renaming a recipe is coat.
Renaming a call site, after the helper exists, is echo.

Vulnerability looks **stable and low** in a specific sense: the
loop did not go back to coat, did not invent a third example
app, and did not put time-travel on the edit form. The object
stayed inside one honesty family. The cost is operator
unreadability and a tick tax per sibling instead of one ship.

That trade is acceptable for keeping the human out of the pick
*only if* a class can still be closed without a human. Oral #67
is that close for temporal echo. The standing-refusals table is
the apprentice handbook so the next class does not reprint
thirty ancestors.

---

## Operator posture

Do not sit in the pick. The loop is allowed its own strategies.
The human's job is to name the object when the language drifts,
and to write a stop that the next agent will treat as an oral
fact rather than as a suggestion.

Standing picture (update this list when a class opens or
closes):

- leftover parse-invent is saturated (oral #42)
- leftover temporal echo is saturated (oral #67)
- leftover catalog id (lens) opened cycle 2184 (oral #68) —
  scan sibling pickers (tab / view / filter enum) next, do not
  walk another temporal ``hx-get``
- Goal B coat stays off

If a week of commit subjects are again `… leftover
include_closed/as_of must ride hx-get`, the stop failed. Say so
once, in oral. Do not take the pick back.
