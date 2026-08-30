# Blue Sky

Orthogonal prototypes of **example-app jobs**, built without Dazzle, then
read for framework gaps. Not a second CRUD admin.

Process: `.agents/skills/blue-sky/SKILL.md`

```bash
.venv/bin/python scripts/blue_sky_spec.py --list-examples
.venv/bin/python scripts/blue_sky_spec.py --example invoice_ops --list-slices
.venv/bin/python scripts/blue_sky_spec.py --example invoice_ops --slice approver --write
```

`specs/` is regenerable from example DSL. `runs/` is disposable
(`node_modules` gitignored).
