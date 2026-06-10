# AWS Deployment

Dazzle generates AWS CDK infrastructure from your DSL specifications. This guide covers the deployment system, configuration options, and TigerBeetle support.

## Overview

The deployment pipeline transforms your DSL into production-ready AWS infrastructure:

```
DSL Files → AppSpec IR → InfraRequirements → AWSRequirements → CDK Stacks
```

### Generated Stacks

| Stack | Purpose | AWS Resources |
|-------|---------|---------------|
| Network | VPC and networking | VPC, Subnets, NAT Gateway, Security Groups |
| TigerBeetle | Financial ledger cluster | EC2 ASG, EBS gp3, SSM Parameters |
| Data | Persistence layer | RDS Aurora, S3 Buckets |
| Messaging | Async communication | SQS Queues, EventBridge |
| Compute | Application runtime | ECS Fargate, ECR, ALB |
| Observability | Monitoring | CloudWatch Dashboards, Alarms |

## Quick Start

```bash
# Generate infrastructure plan
dazzle deploy plan

# Generate CDK code
dazzle deploy generate

# Deploy to AWS (requires AWS credentials)
cd infra && cdk deploy --all
```

## Configuration

Configure deployment in `dazzle.toml`:

```toml
[deploy]
enabled = true
environment = "staging"  # dev, staging, prod
region = "us-east-1"

[deploy.compute]
cpu = 512
memory = 1024
desired_count = 2

[deploy.database]
instance_class = "db.t3.medium"
storage_gb = 100

[deploy.tigerbeetle]
enabled = true
size = "r6i.large"      # t3.medium, r6i.large, r6i.xlarge
node_count = 3          # Must be odd (1, 3, 5) for Raft consensus
volume_size_gb = 100
volume_iops = 10000
```

## Host-App Lifecycle Hooks

When your own code needs startup/shutdown work on the Dazzle app (connection pools, auth caches, background clients), use the supported hook API:

```python
import dazzle

dazzle.register_lifespan_hook(app, startup=init_pool, shutdown=close_pool)
```

Hooks may be sync or async, run inside the framework's lifespan (after the DB pool opens, so they can use the database), and shutdown hooks run in reverse order.

**Do not use `@app.on_event`.** Dazzle constructs the app with a custom `lifespan=`, which makes Starlette skip the default lifespan — the only thing that ever read the `on_event` lists. (Starlette 1.x removed the draining machinery entirely; FastAPI keeps `on_event` only as a deprecated write-only shim.) As of v0.82.24 (#1366) Dazzle drains those legacy handlers itself with original semantics — a failed startup handler aborts boot — and logs a deprecation warning per handler, so existing code works loudly rather than failing silently. Migrate to `register_lifespan_hook`.

## TigerBeetle Support

TigerBeetle is a high-performance financial ledger database. Since AWS has no managed TigerBeetle service, Dazzle deploys a self-hosted cluster on EC2.

### When TigerBeetle is Deployed

TigerBeetle is automatically deployed when your DSL includes `ledger` constructs:

```dsl
ledger CustomerWallet:
  account_code: 1001
  account_type: asset
  currency: GBP
```

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TigerBeetle Cluster                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │   Node 0    │  │   Node 1    │  │   Node 2    │          │
│  │  (Primary)  │←→│  (Replica)  │←→│  (Replica)  │          │
│  │             │  │             │  │             │          │
│  │ EBS gp3     │  │ EBS gp3     │  │ EBS gp3     │          │
│  │ 10K IOPS    │  │ 10K IOPS    │  │ 10K IOPS    │          │
│  └─────────────┘  └─────────────┘  └─────────────┘          │
│         ↑               ↑               ↑                    │
│         └───────────────┴───────────────┘                    │
│                    Port 3001 (Replication)                   │
│                                                              │
│  ECS Services ──────────► Port 3000 (Client)                │
└─────────────────────────────────────────────────────────────┘
```

### Node Count Requirements

| Nodes | Environment | Fault Tolerance |
|-------|-------------|-----------------|
| 1 | Development | None |
| 3 | Production | 1 node failure |
| 5 | High Availability | 2 node failures |

Node count must be **odd** for Raft consensus to achieve quorum.

### Instance Sizing

| Size | Instance Type | Use Case |
|------|---------------|----------|
| `t3.medium` | 2 vCPU, 4GB | Development/testing |
| `r6i.large` | 2 vCPU, 16GB | Small production |
| `r6i.xlarge` | 4 vCPU, 32GB | Medium production |
| `r6i.2xlarge` | 8 vCPU, 64GB | Large production |

### Storage Configuration

TigerBeetle requires high-IOPS storage for its write-ahead log (WAL):

```toml
[deploy.tigerbeetle]
volume_size_gb = 100    # 50-1000 GB
volume_iops = 10000     # 3000-64000 IOPS
```

Recommended IOPS:
- Development: 3,000 (gp3 baseline)
- Production: 10,000+
- High-throughput: 20,000+

### Node Discovery

Nodes discover each other via SSM Parameter Store:

```
/{app-name}/{environment}/tigerbeetle/nodes/{instance-id} = {private-ip}:3000
/{app-name}/{environment}/tigerbeetle/cluster_id = 0
/{app-name}/{environment}/tigerbeetle/replica_count = 3
```

### Connecting from ECS

The generated Compute stack includes the TigerBeetle connection configuration:

```python
# Environment variables injected into ECS tasks
TIGERBEETLE_ADDRESSES = "10.0.1.10:3000,10.0.1.11:3000,10.0.1.12:3000"
TIGERBEETLE_CLUSTER_ID = "0"
```

## Preflight Validation

Before deployment, run preflight checks:

```bash
dazzle deploy preflight
```

### TigerBeetle Validations

| Check | Severity | Description |
|-------|----------|-------------|
| `TB_EVEN_NODE_COUNT` | Critical | Node count must be odd for Raft |
| `TB_INSUFFICIENT_NODES_PROD` | High | Production needs 3+ nodes |
| `TB_LOW_IOPS` | High | IOPS below 5,000 minimum |
| `TB_SUBOPTIMAL_IOPS` | Warn | IOPS below 10,000 recommended |
| `TB_PUBLIC_ACCESS` | Critical | TigerBeetle ports publicly accessible |

## Infrastructure Versioning

Dazzle tracks infrastructure changes via `.dazzle-infra-version.json`:

```json
{
  "version": "a1b2c3d4e5f6",
  "dazzle_version": "0.5.0",
  "generated_at": "2024-01-15T10:30:00Z",
  "environment": "staging",
  "stacks": [
    {"name": "Network", "checksum": "abc123..."},
    {"name": "TigerBeetle", "checksum": "def456..."}
  ]
}
```

Check for changes before regenerating:

```bash
# Shows added/modified/removed stacks
dazzle deploy diff
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Deploy Infrastructure

on:
  push:
    branches: [main]
    paths:
      - 'dsl/**'
      - 'dazzle.toml'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Dazzle
        run: pip install dazzle-dsl

      - name: Generate Infrastructure
        run: dazzle deploy generate

      - name: Run Preflight Checks
        run: dazzle deploy preflight

      - name: Configure AWS
        uses: aws-actions/configure-aws-credentials@v4
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: CDK Deploy
        run: |
          cd infra
          npm install
          npx cdk deploy --all --require-approval never
```

## Security Considerations

### TigerBeetle Security

- **Network Isolation**: TigerBeetle runs in private subnets only
- **No Public Access**: Security groups block all public ingress
- **Encryption**: EBS volumes encrypted at rest
- **IAM**: Minimal permissions via instance role

### Secrets Management

Sensitive values should use AWS Secrets Manager or SSM SecureString:

```toml
[deploy.secrets]
database_password = "ssm:/myapp/prod/db-password"
api_key = "secretsmanager:myapp/api-key"
```

### Row-tenancy RLS roles (`tenancy: mode: shared_schema`)

When an app uses shared-schema row tenancy, the tenant boundary is enforced by PostgreSQL Row-Level Security. **Enforcement only applies when the app connects as a non-superuser, non-owner role** — superusers always bypass RLS, and the table owner bypasses unless `FORCE ROW LEVEL SECURITY` (which Dazzle sets). So:

- **Provision three roles** (DDL generated by `dazzle.back.runtime.rls_schema.build_rls_role_ddl()`):
  - `dazzle_owner` — owns the schema, runs migrations (DDL is unaffected by RLS).
  - `dazzle_app` — the **runtime role** the app connects as. `LOGIN`, **no `BYPASSRLS`**. Subject to every policy.
  - `dazzle_bypass` — `BYPASSRLS`, for excision / cross-tenant ops only (never the app's request path).
- **Point the app's `DATABASE_URL` at `dazzle_app`** in production. If it connects as a superuser/owner, RLS is silently bypassed (data still isolated by the app-layer scope filters, but the DB-level guarantee is lost).
- The runtime sets `dazzle.tenant_id` per transaction from the authenticated user's tenant; an unset context **fails closed** (no rows; writes rejected). Tenant-scoped DB access therefore runs inside a transaction.
- **Local dev** typically connects as a superuser → RLS present but bypassed; app-layer scope filters enforce there. This is expected; production gets the DB-enforced fence via `dazzle_app`.
- **Applying the policies in production (Phase D):** `dazzle db upgrade` now **applies the RLS policies automatically after running migrations** (in `shared_schema` mode), using the same owner-capable role that ran the DDL — so a standard deploy (`dazzle db upgrade`) enforces RLS. You can also apply them explicitly with **`dazzle db apply-rls`** (run with an owner DATABASE_URL). Both are idempotent. **The apply must run as a role that OWNS the tables (`dazzle_owner` / your migration role) — not the runtime `dazzle_app`** (which lacks the privilege to create policies). Pass `--no-rls` to `dazzle db upgrade` to skip (e.g. if you apply RLS in a separate step); a failed apply after a successful migration exits non-zero with a "schema migrated but RLS NOT enforced — re-run `dazzle db apply-rls`" message.
- **Verifying RLS in CI/ops:** `dazzle db verify` now gates **RLS policy drift** (a tenant-scoped table with RLS disabled, or a missing/extra policy) and exits non-zero on drift. `dazzle inspect rls` shows the generated policy set per table (add `--runtime` to cross-reference live `pg_policies`).

## Troubleshooting

### TigerBeetle Cluster Issues

**Nodes not forming cluster:**
```bash
# Check SSM parameters
aws ssm get-parameters-by-path --path "/{app}/{env}/tigerbeetle/nodes"

# Check instance logs
aws logs get-log-events --log-group-name "/{app}/{env}/tigerbeetle"
```

**High latency:**
- Verify IOPS configuration meets requirements
- Check network latency between nodes
- Review CloudWatch metrics for CPU/memory pressure

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `even node count` | 2 or 4 nodes configured | Use 1, 3, or 5 nodes |
| `IOPS below minimum` | Volume IOPS < 5000 | Increase `volume_iops` setting |
| `public access` | 0.0.0.0/0 in security group | Remove public CIDR rules |
