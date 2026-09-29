# Strategy: hyperpart_emitter

Use when `scripts/improve_example_probes.py --status` reports a
`hyperpart_scenarios` row with `planned_emitter > 0` and forces
`framework-ux hyperpart_emitter`.

1. Read the named app and scenario from the probe output. Run
   `dazzle qa hyperpart-opportunities --app <app> --table` and inspect the
   scenario record; do not infer the required emitter from a count alone.
2. Read the matching Hyperpart gallery entry, dual-lock contract, and the
   current DSL-to-render path. Extend the DSL/AppSpec-to-Fragment emitter so
   the app can reach that Hyperpart through normal authoring. Keep UI chrome
   owned by the design-system package and follow its local instructions.
3. Add the smallest parser, IR, render, and example checks needed for the
   specific scenario. Run the relevant dual-lock and example-app gates.
4. Rerun the opportunity probe and `scripts/improve_example_probes.py
   --status`. Claim closure only when the named `planned_emitter` row is gone
   and the example renders through the new path. Record any remaining row in
   the improve backlog with its next concrete action.
