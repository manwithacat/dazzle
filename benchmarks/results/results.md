# invoice_ops Benchmark Results

**Generated:** 2026-05-22T03:21:28.367470+00:00
**Host:** mini
**PostgreSQL:** 17.9 (Homebrew)
**Tenants:** 3
**Iterations per probe:** 200

Schema configs: `default` = framework-generated schema (no FK/scope indexes); `indexed` = + `benchmarks/indexes.sql`.

## List

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 15.0 | 16.6 | 23.5 | 14.1 | 16.4 | 22.8 |
| 10,000 | 15.8 | 18.3 | 27.2 | 15.0 | 17.9 | 23.9 |
| 100,000 | 26.5 | 29.4 | 34.4 | 23.1 | 26.2 | 32.0 |
| 1,000,000 | 79.8 | 84.9 | 87.8 | 79.9 | 84.9 | 86.9 |

## Read

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 16.9 | 21.2 | 26.5 | 15.9 | 18.8 | 22.1 |
| 10,000 | 15.8 | 19.2 | 22.9 | 16.1 | 19.2 | 24.3 |
| 100,000 | 16.2 | 18.5 | 24.1 | 16.1 | 19.2 | 24.8 |
| 1,000,000 | 16.1 | 18.7 | 24.5 | 17.5 | 18.6 | 23.0 |

## Search

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 14.2 | 16.7 | 17.4 | 14.2 | 16.2 | 23.1 |
| 10,000 | 15.8 | 18.7 | 24.1 | 15.4 | 19.2 | 23.3 |
| 100,000 | 26.7 | 29.3 | 33.7 | 22.9 | 25.8 | 32.1 |
| 1,000,000 | 80.2 | 83.9 | 87.9 | 79.1 | 84.0 | 85.4 |

## Aggregate

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 2.5 | 2.9 | 3.0 | 2.7 | 3.0 | 3.2 |
| 10,000 | 6.3 | 7.3 | 10.3 | 6.2 | 7.2 | 7.6 |
| 100,000 | 20.3 | 21.3 | 22.0 | 20.3 | 21.4 | 22.3 |
| 1,000,000 | 141.4 | 143.2 | 144.5 | 140.4 | 142.0 | 142.4 |
