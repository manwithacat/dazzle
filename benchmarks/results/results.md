# invoice_ops Benchmark Results

**Generated:** 2026-05-22T03:15:36.976060+00:00
**Host:** mini
**PostgreSQL:** 17.9 (Homebrew)
**Tenants:** 3
**Iterations per probe:** 200

Schema configs: `default` = framework-generated schema (no FK/scope indexes); `indexed` = + `benchmarks/indexes.sql`.

## List

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 15.2 | 17.1 | 23.6 | 14.8 | 16.7 | 24.3 |
| 10,000 | 20.2 | 23.2 | 28.6 | 18.7 | 22.1 | 33.8 |
| 100,000 | 26.9 | 28.7 | 34.6 | 22.4 | 24.4 | 31.1 |

## Read

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 16.5 | 19.4 | 25.4 | 16.5 | 19.0 | 25.2 |
| 10,000 | 20.5 | 24.3 | 29.4 | 20.5 | 26.8 | 32.5 |
| 100,000 | 16.7 | 19.5 | 24.6 | 16.4 | 18.7 | 24.0 |

## Search

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 15.0 | 16.5 | 24.1 | 15.4 | 17.9 | 23.5 |
| 10,000 | 19.7 | 22.1 | 29.8 | 17.4 | 19.7 | 24.4 |
| 100,000 | 27.0 | 31.4 | 36.9 | 23.5 | 25.8 | 32.7 |

## Aggregate

| Scale (invoices/tenant) | default p50 (ms) | default p95 (ms) | default p99 (ms) | indexed p50 (ms) | indexed p95 (ms) | indexed p99 (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 2.6 | 3.0 | 3.4 | 2.7 | 3.1 | 3.4 |
| 10,000 | 6.7 | 7.9 | 8.6 | 6.7 | 7.5 | 8.2 |
| 100,000 | 20.5 | 21.6 | 23.1 | 20.1 | 21.3 | 22.4 |
