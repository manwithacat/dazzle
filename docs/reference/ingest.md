# Ingest

Declared file and IoT upsert into entities (#1676). Complements seeds (insert-if-missing) and field `file` uploads (one blob on one record).

## DSL

```text
ingest readings_iot:
  entity: Reading
  key: [meter, taken_at]
  protect: source_kind = manual
```

- `entity` — target entity
- `key` — natural key; must match a `unique` constraint on that entity
- `protect` — skip upsert when the existing row matches this equality (manual rows stay)

Parsers for vendor file formats stay in the app. The framework accepts JSON rows, JSONL, or CSV whose headers are field names.

## HTTP

`POST /api/ingest/{name}`

- JSON `{ "rows": [ {...} ], "source_kind": "iot" }` or a JSON array
- Multipart `file` (`.json`, `.jsonl`, `.csv`)
- Auth: `Authorization: Bearer $DAZZLE_INGEST_TOKEN` or `X-Dazzle-Ingest-Token`, or a logged-in session

## Behaviour

1. SHA-256 of the payload: identical bytes are a no-op
2. Each row upserts on `key`; `protect` rows are left alone
3. A completed batch is a HLESS **OBSERVATION** (`ingest:batch_applied`), not a FACT — retries and late IoT samples are expected. `t_log` is ingest time; `t_event` is the earliest timestamp-like value among the declared key fields (domain time, not log-append time). Identical bytes are skipped via content-hash idempotency. Row upserts are current state derived from the observation; they are not FACT records.

See [HLESS Deep Dive](../architecture/hless-deep-dive.md).
