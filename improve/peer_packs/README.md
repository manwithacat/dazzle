# Peer packs (Goal B R3 context)

Short, closed constraint files for `interesting_product` SELECT.

| File | Peer |
|------|------|
| `invoice_ops.toml` | Bill.com / Melio / Tipalti |
| `support_tickets.toml` | Zendesk / Front / Intercom |
| `fieldtest_hub.toml` | TestFlight / Apple Configurator / LabTrack |
| `design_studio.toml` | Figma / Frame.io / Bynder |
| `hr_records.toml` | BambooHR / Workday slice |
| `acme_billing.toml` | Stripe Billing / Chargebee slice |

**Loaded by:** `scripts/interesting_product_portfolio.py` and the
`interesting_product` playbook (answer Peer prompt from pack, not free invent).

**Not residual heat.** Missing pack → agent may still dig; prefer packs when
present. Add packs only for showcase apps with a real commercial peer.
