# Demo Login Matrix

| Tenant | Persona | Email | Password |
|--------|---------|-------|----------|
| Northwind People | hr_admin | hr_admin@demo.dazzle.local | (test-mode / demo) |
| Northwind People | manager | manager@demo.dazzle.local | (test-mode / demo) |
| Northwind People | finance | finance@demo.dazzle.local | (test-mode / demo) |
| Northwind People | employee | employee@demo.dazzle.local | (test-mode / demo) |

Person domain rows share STABLE_PERSONA_USER_IDS with auth principals so
`current_user` scope binds to the matching Person (manager sees Geoff's
reports: Tina + Abdul).
