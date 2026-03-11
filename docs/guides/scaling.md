# Scaling Dazzle Applications

## Why Dazzle Apps Scale Differently

Dazzle apps are DSL-first and server-rendered. There is no separate frontend build, no API gateway, and no client-side state management. This simplicity means fewer moving parts and a different scaling path than traditional SPAs.

| Aspect | Traditional Stack | Dazzle |
|--------|-------------------|--------|
| Frontend | React/Vue SPA, CDN, API gateway | Server-rendered Jinja2 + HTMX |
| API layer | REST/GraphQL microservices | Single FastAPI monolith |
| State | Client-side stores + server | Server-only (PostgreSQL) |
| Deployment units | 3-5 services | 1 process |
| Scaling trigger | API response time | Page render time |

## The Vertical Scaling Path

Most Dazzle apps will never need horizontal scaling. A single server with proper configuration handles hundreds to thousands of concurrent users.

### Stage 1: Fix the Fundamentals

**Connection pooling** and **multi-worker** support handle the vast majority of load issues.

Before (single worker, no pool):
- 1 CPU core utilized
- Fresh TCP connection per database call
- ~50 concurrent users before degradation

After (4 workers, pooled connections):
- 4 CPU cores utilized
- Connections reused from pool
- ~500+ concurrent users

**Configuration:**

```bash
# Environment
export DAZZLE_DB_POOL_MIN=2
export DAZZLE_DB_POOL_MAX=10
export WEB_CONCURRENCY=4

# Or via CLI
dazzle serve --local --workers 4
```

### Stage 2: Smart Vertical Scaling

If Stage 1 isn't enough, these techniques extend capacity without adding infrastructure:

**Edge caching for HTMX responses:**
- HTMX fragments are small HTML snippets
- Cache common fragments at the CDN/reverse proxy level
- Use `Vary: HX-Request` headers for cache correctness

**Read replicas:**
- Route read-heavy surfaces to a PostgreSQL read replica
- Reduces load on the primary database
- Configured at the infrastructure level, transparent to Dazzle

**Larger instance:**
- Double the CPU cores, double the workers
- More RAM = larger connection pool and OS page cache
- Often cheaper than the operational cost of horizontal scaling

### Stage 3: Horizontal Scaling (If Ever Needed)

Dazzle apps are stateless at the process level. Horizontal scaling works by running multiple instances behind a load balancer.

**Requirements:**
- Shared PostgreSQL (already the case)
- Shared Redis for sessions (already the case with `REDIS_URL`)
- Shared file storage (S3 or equivalent for uploads)

**Configuration:**
- Each instance gets its own connection pool
- Advisory locks prevent migration races
- Redis handles session affinity

```bash
# Heroku
heroku ps:scale web=2:standard-2x

# Docker Compose
docker compose up --scale web=4
```

## Monitoring What Matters

| Metric | Where to Check | Action Threshold |
|--------|---------------|------------------|
| Response time (p95) | Application logs | > 500ms |
| Connection pool waits | Dazzle logs | Any "pool exhausted" |
| Database connections | `pg_stat_activity` | > 80% of max |
| Worker memory | OS / platform metrics | > 512MB per worker |
| CPU utilization | OS / platform metrics | > 80% sustained |

## Summary

1. Start with `--workers 4` and connection pooling — this handles most production loads
2. Tune pool size to match your PostgreSQL plan's connection limit
3. Scale vertically (bigger instance) before horizontally (more instances)
4. Dazzle's server-rendered architecture means less infrastructure, not less capacity
