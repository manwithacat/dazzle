# DAZZLE DSL Reserved Keywords

This document lists all reserved keywords in the DAZZLE DSL that cannot be used as field names, entity names, or other identifiers.

**Version**: 0.3.0
**Last Updated**: 2025-11-27

---

## Overview

Reserved keywords are words that have special meaning in the DAZZLE DSL parser. Using these as field names, entity names, or identifiers will cause parse errors.

**Common Error**:
```
Expected identifier or keyword, got <keyword>
```

**Solution**: Use alternative names provided in this document.

---

## Top-Level Structure Keywords

These keywords define the main structure of your DSL files.

| Keyword | Purpose | Use In | Alternatives |
|---------|---------|--------|--------------|
| `module` | Declare module name | File header | N/A (required keyword) |
| `use` | Import dependencies | Module imports | N/A (required keyword) |
| `as` | Rename imports | Module imports | N/A (rarely needed) |
| `app` | Define application | Root declaration | N/A (required keyword) |

---

## Entity-Level Keywords

Keywords used in entity and foreign model definitions.

### Declaration Keywords

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `entity` | Define entity | Top-level | `entity_type`, `record_type` |
| `foreign_model` | External data shape | Integration | `external_model`, `remote_model` |
| `constraint` | Field constraints | Entity fields | `rule`, `validation` |
| `unique` | Uniqueness constraint | Entity fields | `is_unique`, `unique_value` |
| `index` | Database index | Entity fields | `db_index`, `indexed` |
| `key` | Composite key | Entity constraints | `composite_key`, `key_field` |
| `owner` | Ownership field | Entity fields | `owned_by`, `belongs_to` |

### Common Field Name Conflicts

| Reserved | Reason | Suggested Alternatives |
|----------|--------|------------------------|
| `source` | Workspace region source | `data_source`, `origin`, `provider`, `event_source` |
| `url` | Service/foreign_model URLs | `endpoint`, `uri`, `address`, `link` |
| `mode` | Surface mode | `display_mode`, `view_mode`, `type` |
| `status` | Test expectations | `state`, `current_status`, `record_status` |
| `data` | Test setup | `record_data`, `payload`, `content` |
| `created` | Test expectations | `was_created`, `create_status` |
| `filter` | Workspace/test filtering | `filter_by`, `filters`, `filter_criteria` |

---

## Surface-Level Keywords

Keywords used in surface (UI) definitions.

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `surface` | Define UI surface | Top-level | `display_surface`, `view_surface` |
| `uses` | Reference entity | Surface header | `references`, `based_on` |
| `mode` | Surface type | Surface header | `surface_mode`, `view_type` |
| `section` | UI section | Surface body | `panel`, `area`, `region` |
| `field` | Display field | Section body | `display_field`, `shown_field` |
| `action` | User action | Surface/section | `user_action`, `button`, `operation` |
| `read_only` | Field modifier | Field definition | `readonly`, `view_only` |

---

## Experience-Level Keywords

Keywords used in experience (workflow) definitions.

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `experience` | Define workflow | Top-level | `user_experience`, `flow` |
| `step` | Workflow step | Experience body | `workflow_step`, `stage` |
| `kind` | Step type | Step definition | `step_kind`, `type` |
| `start` | Entry point | Experience header | `start_at`, `entry_point` |
| `at` | Step reference | Start declaration | N/A (structural keyword) |
| `on` | Event trigger | Step transitions | `event`, `trigger` |
| `when` | Condition | Conditional logic | `if`, `condition` |
| `submitted` | Form submission event | Step transitions | `on_submit`, `form_submitted` |

---

## Service & Integration Keywords

Keywords for external service integration.

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `service` | Define external API | Top-level | `external_service`, `api_service` |
| `integration` | Connect entities | Top-level | `data_integration`, `sync` |
| `from` | Source specification | Integration | `from_source`, `source_entity` |
| `into` | Target specification | Integration | `into_target`, `target_entity` |
| `with` | Parameters | Multiple contexts | `using`, `params` |
| `call` | Invoke operation | Integration actions | `invoke`, `execute` |
| `map` | Field mapping | Integration | `mapping`, `field_map` |
| `response` | API response | Integration | `api_response`, `result` |
| `match` | Pattern matching | Integration | `pattern`, `matches` |
| `sync` | Synchronization | Integration | `synchronize`, `sync_data` |
| `schedule` | Timing | Integration | `scheduled_at`, `timing` |
| `spec` | OpenAPI spec | Service definition | `specification`, `api_spec` |
| `auth_profile` | Authentication | Service definition | `auth_config`, `credentials` |
| `url` | Service URL | Service definition | `endpoint`, `base_url`, `api_url` |
| `inline` | Inline schema | Service definition | `inline_schema`, `embedded` |
| `operation` | Service operation | Integration | `api_operation`, `method` |
| `mapping` | Field mapping | Integration | `field_mapping`, `transform` |
| `rules` | Transformation rules | Integration | `transform_rules`, `mappings` |
| `scheduled` | Scheduled sync | Integration | `schedule_type`, `periodic` |
| `event_driven` | Event-based sync | Integration | `event_based`, `triggered` |
| `foreign` | Foreign entity ref | Integration | `external`, `remote` |

---

## Test Keywords

Keywords used in test definitions (DAZZLE test DSL).

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `test` | Define test | Top-level | `test_case`, `spec` |
| `setup` | Test setup | Test body | `test_setup`, `preconditions` |
| `data` | Test data | Setup | `test_data`, `fixtures` |
| `expect` | Assertions | Test body | `expected`, `assertion` |
| `status` | HTTP status | Expectations | `http_status`, `response_status` |
| `created` | Creation check | Expectations | `was_created`, `is_created` |
| `filter` | Filter results | Test queries | `filter_by`, `where` |
| `search` | Search operation | Test queries | `search_for`, `find` |
| `order_by` | Sort order | Test queries | `sort_by`, `ordered_by` |
| `count` | Count results | Expectations/aggregates | `total_count`, `num_records` |
| `error_message` | Error text | Expectations | `error_text`, `message` |
| `first` | First result | Test queries | `first_record`, `initial` |
| `last` | Last result | Test queries | `last_record`, `final` |
| `query` | Query operation | Test actions | `query_for`, `fetch` |
| `create` | Create operation | Test actions | `create_record`, `add` |
| `update` | Update operation | Test actions | `update_record`, `modify` |
| `delete` | Delete operation | Test actions | `delete_record`, `remove` |
| `get` | Get operation | Test actions | `fetch`, `retrieve` |

---

## Workspace & UX Keywords

Keywords for workspace and UX semantic layer (v0.2+).

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `workspace` | Define workspace | Top-level | `user_workspace`, `dashboard` |
| `ux` | UX customization | Various | `user_experience`, `ui_config` |
| `purpose` | Workspace purpose | Workspace header | `description`, `goal` |
| `source` | Data source | Workspace regions | `data_source`, `entity_source`, `origin` |
| `limit` | Result limit | Workspace regions | `max_results`, `top_n` |
| `display` | Display mode | Workspace regions | `view_mode`, `presentation` |
| `aggregate` | Aggregations | Workspace regions | `aggregates`, `metrics` |
| `filter` | Filtering | Workspace regions | `filter_by`, `where_clause` |
| `show` | Show fields | UX | `display_fields`, `visible` |
| `hide` | Hide fields | UX | `hidden_fields`, `exclude` |
| `sort` | Sort order | UX | `sort_by`, `order` |
| `empty` | Empty state | UX | `no_data_message`, `placeholder` |
| `attention` | Attention signals | UX | `priority`, `importance` |
| `message` | Message text | UX | `text`, `content` |
| `for` | Scoping | UX | `applies_to`, `scope` |
| `scope` | Scope definition | UX | `applies_to`, `context` |
| `defaults` | Default values | UX | `default_values`, `initial` |
| `focus` | Focus element | UX | `focused_field`, `highlight` |
| `group_by` | Grouping | Workspace/UX | `grouped_by`, `partition_by` |
| `list` | List display | Display modes | `list_view`, `items` |
| `grid` | Grid display | Display modes | `grid_view`, `table` |
| `timeline` | Timeline display | Display modes | `timeline_view`, `chronological` |
| `show_aggregate` | Show aggregations | UX | `show_metrics`, `display_totals` |
| `action_primary` | Primary action | UX | `main_action`, `default_action` |
| `all` | All items | Filtering | `all_items`, `everything` |

### Special UX Attention Keywords

| Keyword | Purpose | Alternatives |
|---------|---------|--------------|
| `critical` | Critical attention | `urgent`, `high_priority` |
| `warning` | Warning attention | `warn`, `alert`, `caution` |
| `notice` | Notice attention | `notification`, `advisory` |
| `info` | Info attention | `information`, `detail` |

**Note**: These are especially problematic in enum values.

---

## Expression & Condition Keywords

Keywords used in conditional expressions and filters.

| Keyword | Purpose | Use In | Alternatives for Field Names |
|---------|---------|--------|------------------------------|
| `where` | Filter condition | Aggregates/queries | `filter_where`, `condition` |
| `and` | Logical AND | Conditions | `and_condition`, `both` |
| `or` | Logical OR | Conditions | `or_condition`, `either` |
| `not` | Logical NOT | Conditions | `not_condition`, `inverse` |
| `in` | Membership test | Conditions | `in_list`, `contains` |
| `is` | Identity/null test | Conditions | `equals`, `is_equal` |
| `asc` | Ascending sort | Sort expressions | `ascending`, `sort_asc` |
| `desc` | Descending sort | Sort expressions | `descending`, `sort_desc` |

### Operators

| Symbol | Meaning | Alternatives for Field Names |
|--------|---------|------------------------------|
| `!=` | Not equal | `not_equal`, `ne` |
| `>` | Greater than | `greater_than`, `gt` |
| `<` | Less than | `less_than`, `lt` |
| `>=` | Greater or equal | `greater_equal`, `gte` |
| `<=` | Less or equal | `less_equal`, `lte` |

---

## Boolean Literals

| Keyword | Purpose | Alternatives for Field Names |
|---------|---------|------------------------------|
| `true` | Boolean true | `is_true`, `enabled` |
| `false` | Boolean false | `is_false`, `disabled` |

**Note**: Use these for boolean default values, not as field names.

---

## Common Pitfalls

### Problem: Enum values conflict with keywords

**Bad**:
```dsl
entity Alert:
  severity: enum[info,warning,error,critical]=warning
```

**Error**: `Expected identifier, got warning` and `error`

**Good**:
```dsl
entity Alert:
  severity: enum[info,warn,err,critical]=warn
```

**Alternatives**:
- `warning` → `warn`, `alert`, `caution`
- `error` → `err`, `fail`, `failure`, `fault`
- `critical` → `crit`, `urgent`, `severe`
- `info` → `information`, `detail` (or keep `info` if not in conflicting context)

---

### Problem: Field name conflicts with workspace keywords

**Bad**:
```dsl
entity Service:
  source: str(200)  # Reserved for workspace regions
  url: str(500)     # Reserved for service definitions
```

**Error**: `Expected :, got NEWLINE`

**Good**:
```dsl
entity Service:
  data_source: str(200)
  endpoint: str(500)
```

---

### Problem: Test data field conflicts

**Bad**:
```dsl
test "Create task":
  setup:
    data:
      status: "active"  # Reserved for test expectations
      created: "2025-01-01"  # Reserved for test expectations
```

**Good**:
```dsl
test "Create task":
  setup:
    data:
      current_status: "active"
      created_at: "2025-01-01"
```

---

## Quick Reference by Category

### Absolutely Avoid (High Conflict)

These cause errors in most contexts:

- `url` → use `endpoint`, `uri`, `address`
- `source` → use `data_source`, `origin`, `provider`
- `error` → use `err`, `failure`, `fault`
- `warning` → use `warn`, `alert`, `caution`
- `status` → use `state`, `current_status`
- `data` → use `record_data`, `content`, `payload`
- `filter` → use `filter_by`, `where_clause`
- `mode` → use `display_mode`, `type`

### Context-Dependent (Sometimes Safe)

These may work in some contexts but not others:

- `message` (safe in entity fields, reserved in UX)
- `info` (safe in entity fields, reserved in UX attention)
- `count` (safe in entity fields, reserved in aggregates)
- `created` (safe as `created_at` field, reserved in test expectations)
- `focus` (safe in entity fields, reserved in UX)

### Safe with Prefixes

Add prefixes to avoid conflicts:

- `user_mode` instead of `mode`
- `alert_source` instead of `source`
- `api_url` instead of `url`
- `record_status` instead of `status`
- `error_code` instead of `error`

---

## Parser Behavior

### How Keywords Are Detected

1. Lexer tokenizes input into keywords and identifiers
2. Keywords are matched case-sensitively (`url` is reserved, `URL` is not)
3. In field name position, keywords cause parse errors
4. In enum values, keywords cause parse errors

### Error Messages

Current error (v0.3.0):
```
Expected identifier or keyword, got <keyword>
Expected :, got NEWLINE
```

Future enhancement (v0.3.1+):
```
Field name 'url' is reserved keyword. Suggested alternatives: endpoint, uri, address
```

---

## Getting Help

If you encounter a reserved keyword error:

1. Check this document for suggested alternatives
2. Add a prefix/suffix to the identifier
3. Use an alternative name that doesn't conflict
4. Report ambiguous cases as GitHub issues

---

## Version History

- **v0.3.0** (2025-11-27): Initial comprehensive reserved keywords reference
- **v0.2.0**: Added workspace and UX keywords
- **v0.1.0**: Core entity, surface, and integration keywords

---

**See Also**:
- [DSL Reference](DAZZLE_DSL_REFERENCE_0_1.md)
- [DSL Grammar](DAZZLE_DSL_GRAMMAR_0_1.ebnf)
- [Examples](../examples/)
