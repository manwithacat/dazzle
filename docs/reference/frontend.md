# Frontend & Templates

> **Auto-generated** from knowledge base TOML files by `docs_gen.py`.
> Do not edit manually; run `dazzle docs generate` to regenerate.

The Dazzle frontend uses server-rendered Jinja2 templates with HTMX for declarative HTTP interactions. This page covers the three-layer template architecture, fragment contracts, out-of-band swaps, sitespec configuration, copy management, section types, and static asset serving.

---

## Htmx

Declarative HTTP interaction layer for Dazzle-generated frontends. All interactions expressed via HTML attributes (hx-get, hx-post, hx-target, hx-swap, hx-trigger). Server renders HTML fragments; HTMX swaps them into the DOM.

### Syntax

```dsl
<element
  hx-{verb}="/endpoint"   <!-- get, post, put, delete -->
  hx-target="#target-id"
  hx-swap="innerHTML"     <!-- innerHTML, outerHTML, beforeend, etc. -->
  hx-trigger="click"      <!-- click, keyup, change, load, etc. -->
  hx-indicator="#spinner">
```

### Example

```dsl
<!-- Debounced search -->
<input type="text"
  hx-get="/api/search"
  hx-target="#results"
  hx-trigger="keyup changed delay:400ms"
  hx-indicator="#search-spinner">

<!-- Row click navigation -->
<tr hx-get="/contacts/{{ id }}"
    hx-target="body"
    hx-push-url="true">

<!-- Inline delete with confirmation -->
<button hx-delete="/api/tasks/{{ id }}"
        hx-target="closest tr"
        hx-swap="outerHTML"
        hx-confirm="Delete this task?">
```

**Related:** [Templates](frontend.md#templates), [Fragment Contract](frontend.md#fragment-contract), [Oob Swap](frontend.md#oob-swap)

---

## Templates

Three-layer Jinja2 template architecture: Components (full page content), Fragments (HTMX-swappable partials), Macros (pure rendering helpers). Each layer has distinct responsibilities.

### Syntax

```dsl
templates/
├── base.html                 # Document shell
├── components/               # Full page content (one per surface mode)
│   ├── list_view.html
│   ├── detail_view.html
│   └── form_edit.html
├── fragments/                # HTMX-swappable partials
│   ├── table_rows.html
│   ├── search_select.html
│   └── form_errors.html
└── macros/                   # Pure rendering helpers
    ├── form_field.html
    └── table_cell.html
```

**Related:** [Htmx](frontend.md#htmx), [Fragment Contract](frontend.md#fragment-contract), [Surface](surfaces.md#surface)

---

## Fragment Contract

A fragment's formal interface specifying required/optional params, events it emits, events it listens to, and swap targets. Enables LLM agents to compose fragments without reading implementation.

### Syntax

```dsl
fragment: <name>
template: fragments/<name>.html

params:
  required: [field.name, field.label, endpoint]
  optional: [placeholder, debounce_ms]

emits: [itemSelected, formSaved]
listens: [searchCleared]

swap_targets: ["#{{ field.name }}-results"]
oob_targets: ["#field-{{ autofill_target }}"]
```

### Example

```dsl
# Discovery before modification
mcp__dazzle__dsl(operation="list_fragments")

# Returns structured contracts:
{
  "search_select": {
    "params": ["field.name", "field.source.endpoint", ...],
    "emits": ["itemSelected"],
    "listens": [],
    "description": "Debounced search with autofill"
  }
}
```

**Related:** [Templates](frontend.md#templates), [Htmx](frontend.md#htmx)

---

## Oob Swap

Out-of-band swap pattern (hx-swap-oob) for updating multiple DOM elements from a single server response. Used for autofill: selecting a search result populates multiple related form fields.

### Syntax

```dsl
<!-- Server response includes multiple elements -->

<!-- Primary swap (goes to hx-target) -->
<div id="search-selected">Selected: Acme Ltd</div>

<!-- OOB swaps (go to their own ids) -->
<input id="field-company_number" value="12345678"
       hx-swap-oob="outerHTML" readonly />
<input id="field-status" value="active"
       hx-swap-oob="outerHTML" readonly />
```

### Example

```dsl
# Python endpoint returning OOB response
from dazzle_back.runtime.htmx import render_oob_fields

@router.get("/select/{id}")
async def select_company(id: str):
    company = await get_company(id)
    return render_oob_fields(
        primary=f"Selected: {company.name}",
        autofill={
            "company_number": company.number,
            "company_status": company.status,
        }
    )
```

**Related:** [Htmx](frontend.md#htmx), [Fragment Contract](frontend.md#fragment-contract), Search Select

---

## Sitespec

Site configuration file (sitespec.yaml) defining brand, navigation, page structure, legal pages, auth pages, and integrations. Structural configuration for the marketing/public site shell. Pages use typed sections (hero, features, cta, markdown, comparison, card_grid, trust_bar, etc.) and can be hybrid — mixing structured sections with markdown content blocks. See 'section_types' for all available section types.

### Syntax

```dsl
# site/sitespec.yaml
version: "1.0"
brand:
  product_name: "FreshMeals"
  tagline: "Chef-quality meals delivered"
  support_email: "support@freshmeals.com"
layout:
  nav:
    public:
      - label: "Features"
        href: "/features"
  footer:
    columns:
      - title: "Product"
        links: [...]
pages:
  - route: "/"
    type: landing
    sections:
      - type: hero
        headline: "Chef-quality meals"
      - type: markdown                    # Inline markdown section
        source:
          path: "pages/our-story.md"
          format: md
      - type: comparison                  # Structured comparison table
        headline: "How we compare"
        columns:
          - label: "Us"
            highlighted: true
          - label: "Competitor"
        items:
          - feature: "Delivery"
            cells: ["Same day", "3-5 days"]
      - type: card_grid
        headline: "Our plans"
        items:
          - title: "Starter"
            body: "For individuals"
            icon: "user"
            cta:
              label: "Choose"
              href: "/signup?plan=starter"
      - type: trust_bar
        items:
          - text: "SOC 2 Certified"
            icon: "shield-check"
          - text: "99.9% Uptime"
      - type: cta
        headline: "Ready to eat well?"
        primary_cta:
          label: "Start Free Trial"
          href: "/signup"
```

### Example

```dsl
# Hybrid page: structured sections + markdown content
pages:
  - route: "/about"
    type: landing
    title: "About Us"
    sections:
      - type: hero
        headline: "About Our Company"
        subhead: "Building the future of food delivery"
      - type: markdown
        source:
          path: "pages/about-story.md"
          format: md
      - type: split_content
        headline: "Built for teams"
        body: "Collaborate in real time."
        media:
          kind: image
          src: "/img/team.png"
          alt: "Team collaboration"
        alignment: right
      - type: value_highlight
        headline: "10x faster deliveries"
        subhead: "Ship with confidence"
        body: "Our platform reduces delivery time by 90%."
        primary_cta:
          label: "Try Free"
          href: "/signup"
      - type: cta
        headline: "Join us today"
        primary_cta:
          label: "Sign Up"
          href: "/signup"
```

**Related:** [Copy Md](frontend.md#copy-md), Site Coherence, [Section Types](frontend.md#section-types), [Hybrid Pages](frontend.md#hybrid-pages)

---

## Copy Md

Founder-friendly markdown file for PROSE marketing content. Best for: hero headlines, feature descriptions, testimonials, FAQ text. NOT for structured data like pricing tiers — those belong in sitespec.yaml. Supports :::type directive fences to create typed sections inline (see 'directive_syntax').

### Syntax

```dsl
# site/content/copy.md

# Hero
**Your Headline Here**
Subheadline text explaining the value proposition.
[Get Started](/signup) | [Learn More](/features)

---

# Features
## Fast Performance
Description of the speed benefit. [icon: bolt]

## Easy to Use
Description of the UX benefit. [icon: sparkles]

---

# Testimonials
> "This transformed our workflow!"
> — Jane Smith, CEO at Acme Inc

---

# FAQ
## What is this product?
Clear answer explaining the product.

## How do I get started?
Step by step instructions.
```

### Example

```dsl
# Hero
**Run your business, not your admin**
Automate repetitive tasks and focus on growth.
[Start Free Trial](/signup)

---

# Features
## Automated Workflows
Set up once, run forever. No coding required. [icon: bolt]

## Real-time Analytics
See what matters, when it matters. [icon: chart]
```

**Related:** [Sitespec](frontend.md#sitespec), Site Coherence, [Directive Syntax](frontend.md#directive-syntax), [Section Types](frontend.md#section-types)

---

## Section Types

All available section types for sitespec.yaml page sections. Each section has a 'type' field and type-specific fields on SectionSpec. Sections are rendered client-side by the site_renderer.py JS engine. IR models are in dazzle.core.ir.sitespec.

### Syntax

```dsl
# Available section types and their key fields:
# All sections support: id (optional anchor ID for deep links)

# hero — Main landing section
- type: hero
  id: "hero"             # optional: explicit anchor ID
  headline: "..."
  subhead: "..."
  body: "..."
  primary_cta: {label: "...", href: "..."}
  secondary_cta: {label: "...", href: "..."}
  media: {kind: image, src: "...", alt: "..."}

# features — Feature grid
- type: features
  headline: "..."
  items:  # list of {title, description, icon}

# testimonials — Customer quotes
- type: testimonials
  headline: "..."
  items:  # list of {quote, name, role, attribution}

# pricing — Pricing tiers
- type: pricing
  headline: "..."
  items:  # list of {name, price, period, features, cta}

# faq — Q&A accordion
- type: faq
  headline: "..."
  items:  # list of {question, answer}

# cta — Call-to-action block
- type: cta
  headline: "..."
  subhead: "..."
  primary_cta: {label: "...", href: "..."}

# markdown — Embedded markdown content (hybrid pages)
- type: markdown
  source:
    path: "pages/about.md"   # relative to site/content/
    format: md               # md or html

# comparison — Feature comparison table
- type: comparison
  headline: "..."
  columns:                   # list of ComparisonColumn
    - label: "Us"
      highlighted: true      # optional, highlights the column
    - label: "Competitor"
  items:                     # list of ComparisonRow
    - feature: "Price"
      cells: ["$29", "$49"]  # one cell per column

# value_highlight — Large typography callout
- type: value_highlight
  headline: "10x faster"
  subhead: "Ship with confidence"
  body: "Detailed explanation..."
  primary_cta: {label: "Try Free", href: "/signup"}

# split_content — Text + image side-by-side
- type: split_content
  headline: "Built for teams"
  body: "Collaborate in real time."
  media: {kind: image, src: "/img/team.png", alt: "Team"}
  alignment: right           # left (default) or right

# card_grid — Cards with per-card CTAs
- type: card_grid
  headline: "Solutions"
  items:                     # list of CardItem
    - title: "Feature A"
      body: "Description"
      icon: "zap"            # optional icon name
      cta:                   # optional per-card CTA
        label: "Learn More"
        href: "/features/a"

# trust_bar — Horizontal signal strip
- type: trust_bar
  items:                     # list of TrustBarItem
    - text: "SOC 2 Certified"
      icon: "shield-check"   # optional icon name
    - text: "99.9% Uptime"
```

### Example

```dsl
# A landing page using multiple section types
pages:
  - route: "/"
    type: landing
    title: "Home"
    sections:
      - type: hero
        headline: "Ship Faster"
        subhead: "The developer platform"
        primary_cta:
          label: "Get Started"
          href: "/signup"
      - type: trust_bar
        items:
          - text: "SOC 2"
            icon: "shield-check"
          - text: "GDPR"
          - text: "99.9% Uptime"
      - type: features
        headline: "Why choose us"
        items:
          - title: "Fast"
            description: "Blazing speed"
            icon: "bolt"
          - title: "Secure"
            description: "Enterprise grade"
            icon: "shield"
      - type: comparison
        headline: "How we compare"
        columns:
          - label: "Us"
            highlighted: true
          - label: "Competitor A"
          - label: "Competitor B"
        items:
          - feature: "Price"
            cells: ["$29/mo", "$49/mo", "$99/mo"]
          - feature: "SSO"
            cells: ["Included", "Add-on", "Enterprise only"]
      - type: card_grid
        headline: "Use cases"
        items:
          - title: "Startups"
            body: "Ship your MVP fast"
            icon: "rocket"
            cta:
              label: "Learn more"
              href: "/startups"
      - type: value_highlight
        headline: "10x faster deployments"
        body: "Our platform reduces deploy time by 90%."
        primary_cta:
          label: "See the data"
          href: "/benchmarks"
      - type: cta
        headline: "Ready to start?"
        primary_cta:
          label: "Sign Up Free"
          href: "/signup"
```

**Related:** [Sitespec](frontend.md#sitespec), [Hybrid Pages](frontend.md#hybrid-pages), [Directive Syntax](frontend.md#directive-syntax)

---

## Directive Syntax

Directive fence syntax for embedding typed sections inside markdown content files. Use :::type to open a directive block and ::: to close it. Prose between fences becomes markdown sections. Reuses copy_parser section parsers for typed blocks. Source: dazzle.core.directive_parser.

### Syntax

```dsl
# In any markdown content file (e.g. site/content/pages/about.md)

Prose paragraph — rendered as a markdown section.

:::features
## Fast Performance
Our app is blazingly fast.

## Easy to Use
Simple and intuitive interface.
:::

More prose here — becomes another markdown section.

:::cta
## Ready to start?
[Sign Up Free](/signup)
:::
```

### Example

```dsl
# site/content/pages/landing.md
# This file produces 5 sections when processed:

Welcome to our platform. We make development easy.

:::hero
**Ship Faster Than Ever**
The platform built for modern teams.
[Get Started](/signup)
:::

Our customers love us because we focus on what matters.

:::features
## Automated Deploys
Push to main, we handle the rest.

## Real-time Monitoring
See everything at a glance.
:::

:::faq
## What languages do you support?
All major languages and frameworks.

## Is there a free tier?
Yes, free for up to 3 projects.
:::

Ready to join? Start your free trial today.
```

**Related:** [Copy Md](frontend.md#copy-md), [Section Types](frontend.md#section-types), [Hybrid Pages](frontend.md#hybrid-pages)

---

## Hybrid Pages

Hybrid pages mix structured sections (hero, cta, comparison) with markdown content blocks in a single page. Use type: markdown sections with a source.path to embed .md files inline alongside structured sections. This enables rich content pages that combine the flexibility of markdown with the structure of typed sections.

### Syntax

```dsl
# Hybrid page in sitespec.yaml
pages:
  - route: "/about"
    type: landing
    title: "About Us"
    sections:
      # Structured section
      - type: hero
        headline: "About Our Company"

      # Markdown content block (loaded from file)
      - type: markdown
        source:
          path: "pages/about-story.md"
          format: md

      # Another structured section
      - type: cta
        headline: "Join us"
        primary_cta:
          label: "Sign Up"
          href: "/signup"
```

### Example

```dsl
# Example: /about page mixing 3 section types
# sitespec.yaml:
pages:
  - route: "/about"
    type: landing
    title: "About"
    sections:
      - type: hero
        headline: "Our Story"
        subhead: "From garage to global"
      - type: markdown
        source:
          path: "pages/about-founding.md"
      - type: split_content
        headline: "Our Mission"
        body: "Making technology accessible to everyone."
        media:
          kind: image
          src: "/img/mission.png"
          alt: "Mission"
        alignment: right
      - type: markdown
        source:
          path: "pages/about-team.md"
      - type: trust_bar
        items:
          - text: "Founded 2020"
          - text: "500+ Customers"
          - text: "SOC 2 Certified"

# site/content/pages/about-founding.md:
# (plain markdown — rendered as HTML at runtime)
We started in a garage with a simple idea...

# site/content/pages/about-team.md:
Meet the people behind the product...
```

**Related:** [Sitespec](frontend.md#sitespec), [Section Types](frontend.md#section-types), [Directive Syntax](frontend.md#directive-syntax), [Copy Md](frontend.md#copy-md)

---

## Static Assets

Static asset serving convention for Dazzle projects. Project-level images and assets are placed in {project_root}/static/ and served at /static/*. Framework assets (dz.js, dz.css, favicon) are served automatically from the framework directory. Project files take priority over framework files when paths overlap (shadow/override).

### Syntax

```dsl
# Project directory layout:
my-project/
├── static/
│   └── images/
│       ├── hero-office.webp      # → /static/images/hero-office.webp
│       ├── logo.png              # → /static/images/logo.png
│       └── team-photo.jpg        # → /static/images/team-photo.jpg
├── dsl/
├── site/
└── dazzle.toml

# Framework assets (served automatically):
/static/js/dz.js                   # Dazzle micro-runtime
/static/css/dazzle.css             # Dazzle base styles
/static/assets/dazzle-favicon.svg  # Favicon
```

### Example

```dsl
# In sitespec.yaml — reference project images:
pages:
  - route: "/"
    type: landing
    sections:
      - type: hero
        headline: "Welcome"
        media:
          kind: image
          src: "/static/images/hero-office.webp"
          alt: "Office"
      - type: split_content
        headline: "Our team"
        media:
          kind: image
          src: "/static/images/team-photo.jpg"
          alt: "Team photo"
        alignment: right

# The scaffold command creates static/images/ automatically:
# sitespec(operation="scaffold")
```

**Related:** [Sitespec](frontend.md#sitespec), [Section Types](frontend.md#section-types)

---
