---
name: dbt-semantic-layer
description: How to annotate dbt models so dbt-cube-sync generates Cube.js schemas — covers all three formats (config.meta.metrics, MetricFlow v1 standalone, MetricFlow v2 inline)
---

# dbt Semantic Layer Formats

`dbt-cube-sync` reads `manifest.json` and supports three annotation formats. All three can coexist in the same project.

**Default: use Format 3 (MetricFlow v2 inline) unless the user asks for something else.** It keeps semantic layer definitions co-located with the model YAML, works with dbt 1.9+ and dbt-fusion 2.x, and is the direction dbt is investing in. Use Format 1 only when dbt version is below 1.5 or the project already uses `config.meta.metrics`. Use Format 2 when the team prefers semantic model definitions in a dedicated file rather than inline.

**Minimum versions:** dbt 1.9+ or dbt-fusion 2.x; `dbt-cube-sync` 0.1.0a46+; `dbt_simple_metrics` 1.0.9+ (if used).

**Non-negotiable rules:**
- Every metric and every dimension must have a `label:` and a `description:`. They appear in downstream BI tools and power semantic search — a metric without them is incomplete.
- dbt is the single source of truth. Generated Cube.js files and BI datasets are never edited by hand.
- Tune query performance at the warehouse level (materialization strategy, clustering, sort/distribution keys). Cube pre-aggregations are a supported escape hatch but should not be the first tool reached for.

---

## Format 1 — `config.meta.metrics` (legacy, any dbt version)

Metrics live in `config.meta.metrics` on the model node. No `semantic_model:` or MetricFlow keywords needed. Works with any dbt version.

```yaml
# models/orders.yml
version: 2
models:
  - name: orders
    config:
      meta:
        metrics:
          order_count:
            type: count
          revenue:
            type: sum
            sql: amount
          avg_order_value:
            type: number
            sql: "${revenue}::float / nullif(${order_count}, 0)"
            format: percent   # → Cube.js format: 'percent'
          recent_revenue:
            type: sum
            sql: amount
            filter: "${CUBE}.created_at >= now() - interval '30 days'"
```

Supported `type` values: `sum`, `count`, `avg`, `min`, `max`, `countDistinct`, `countDistinctApprox`, `runningTotal`, `number`.

Column types come from `data_type:` on the column, `catalog.json`, or the database.

---

## Format 2 — MetricFlow v1 standalone (dbt 1.5–1.11)

Semantic models and metrics live in separate top-level YAML blocks, usually in their own file (e.g. `models/semantic_models.yml`).

```yaml
# models/semantic_models.yml
version: 2

semantic_models:

  - name: semantic_orders
    model: ref('orders')

    entities:
      - name: order_id          # becomes Cube.js primaryKey dimension
        type: primary
        expr: order_id
        label: "Order ID"
      - name: customer_id       # foreign key → generates Cube.js join
        type: foreign
        expr: customer_id
        label: "Customer ID"

    dimensions:
      - name: status
        type: categorical
        label: "Status"
        description: "Order status (pending, shipped, delivered)."
      - name: region
        type: categorical
        label: "Region"
      - name: created_at
        type: time
        label: "Created At"
        type_params:
          time_granularity: day

    measures:
      - name: order_count
        agg: count_distinct
        expr: order_id
        agg_time_dimension: created_at
      - name: revenue
        agg: sum
        expr: amount
        agg_time_dimension: created_at
      - name: non_odp_revenue     # CASE WHEN in measure → filtering pattern
        agg: sum
        expr: "case when is_odp = 0 then amount else null end"
        agg_time_dimension: created_at

    config:
      meta:
        pre_aggregations:          # optional rollup caching
          orders_by_region_monthly:
            type: rollup
            measures:    [total_revenue]
            dimensions:  [region]
            time_dimension: created_at
            granularity: month
            refresh_key:
              every: "1 day"

metrics:

  - name: total_revenue
    label: "Total Revenue"
    description: "Sum of all order amounts."
    type: simple
    type_params:
      measure: revenue            # points to a measure in a semantic model

  - name: avg_order_value
    label: "Avg Order Value"
    type: derived
    type_params:
      expr: total_revenue / order_count
      metrics:
        - name: total_revenue
        - name: order_count

  - name: conversion_rate
    label: "Conversion Rate"
    type: ratio
    type_params:
      numerator: total_revenue
      denominator: order_count
    meta:
      format: "percent"           # → Cube.js format: 'percent'

  - name: cumulative_revenue
    label: "Cumulative Revenue"
    type: cumulative
    type_params:
      measure: revenue

  - name: active_revenue          # metric-level filter
    label: "Active Order Revenue"
    type: simple
    type_params:
      measure: revenue
    meta:
      filter: "${CUBE}.status = 'active'"
```

**Metric types:**

| type | description | type_params fields |
|------|-------------|-------------------|
| `simple` | wraps one base measure | `measure: <name>` |
| `derived` | expression over other metrics | `expr:`, `metrics: [{name:}]` |
| `ratio` | numerator / denominator | `numerator:`, `denominator:` (names or `{name:}` objects) |
| `cumulative` | running total over time | `measure: <name>` |

**Format and filter placement:**
- `format:` and `filter:` belong on the **metric** (under `meta:`), not the measure.
- Measure-level filters use CASE WHEN in `expr:` (the standard MetricFlow pattern).
- Metric `filter:` uses `${CUBE}.col` syntax — dbt renders `{{ }}` as Jinja2, so avoid it here.

---

## Format 3 — MetricFlow v2 inline (dbt 1.9+ / dbt-fusion 2.x)

The semantic model is embedded directly inside the model's `.yml` file. Each column carries its `entity:` or `dimension:` role, and metrics are listed at the model level. dbt compiles everything into `manifest['semantic_models']` and `manifest['metrics']`.

```yaml
# models/attendance_by_student_date.yml
version: 2
models:

  - name: attendance_by_student_date
    description: "One row per student per in-session day."

    semantic_model:
      enabled: true

    agg_time_dimension: date_of_attendance  # default time dim for all metrics

    columns:
      # --- entities (join keys) ---
      - name: student_id_date
        config:
          meta:
            primary-key: true      # → Cube.js primaryKey: true
        entity:
          type: primary

      - name: year_id
        entity:
          type: foreign

      - name: student_id
        entity:
          type: foreign

      # --- time dimension ---
      - name: date_of_attendance
        granularity: day
        dimension:
          type: time

      # --- categorical dimensions ---
      - name: school_year
        dimension:
          type: categorical

      - name: grade_level
        dimension:
          type: categorical

      - name: presence_status_cd
        dimension:
          type: categorical

    metrics:
      - name: present_days
        description: "Days present, excluding ODP students."
        type: simple
        agg: sum
        expr: >
          case
            when current_odp <> 0 then 0
            when presence_status_cd is null then 1
            when upper(presence_status_cd) = 'PRESENT' then 1
            else 0
          end
        fill_nulls_with: 0

      - name: total_days_enrolled
        type: simple
        agg: sum
        expr: "case when current_odp = 0 then 1 else 0 end"
        fill_nulls_with: 0

      - name: total_days_enrolled_including_odp
        type: simple
        agg: count
        expr: date_of_attendance    # agg: count → Cube.js type: count (COUNT(*))
        fill_nulls_with: 0

    config:
      meta:
        owner: [data-team@example.com]
        contains_pii: true
```

**Key rules for Format 3:**
- `semantic_model: enabled: true` opts the model into MetricFlow processing.
- Column roles are set with `entity: type:` (primary/foreign) or `dimension: type:` (categorical/time).
- `agg_time_dimension:` at the model level sets the default time dimension.
- Metrics are a list under `metrics:` on the model, each with `type: simple`, `agg:`, and `expr:`.
- `agg: count` without a meaningful `expr` becomes `COUNT(*)` in Cube.js (omit the `sql` field).
- `fill_nulls_with:` is a MetricFlow hint; it is not forwarded to Cube.js.

---

## Common patterns across all formats

### CASE WHEN in measure expressions

Use CASE WHEN inside `expr:` / `sql:` to implement conditional aggregation (the preferred pattern for exclusion logic):

```yaml
# Format 1
sql: "case when is_odp = 0 then amount else null end"

# Format 2 / 3
expr: "case when is_odp = 0 then amount else null end"
```

### Backtick safety in descriptions

Descriptions are written as JavaScript template literals in the generated Cube.js file. Any backtick in a description is automatically replaced with a single quote by the generator, so raw SQL examples in descriptions are safe to write.

### Cross-model joins (Formats 2 and 3)

A `foreign` entity whose name matches a `primary` or `unique` entity on another semantic model automatically generates a Cube.js `joins:` block with `many_to_one` cardinality.

### Pre-aggregations (Formats 1 and 2)

Add `pre_aggregations:` under `config.meta` on a semantic model (or directly in `config.meta` for Format 1). The `measures` and `dimensions` lists reference names in the cube; `time_dimension` references a time dimension name.

### `format` and `filter` on metrics

**Formats 1 and 2** — both go under `meta:` on the metric:
```yaml
meta:
  format: "percent"
  filter: "${CUBE}.status = 'active'"
```

**Format 3** — `filter:` and `format:` follow different rules because one is native MetricFlow and the other is not:

| Field | Placement | Syntax |
|-------|-----------|--------|
| `filter:` | top-level on the metric | `{{ Dimension('entity__col') }} = 'val'` |
| `format:` | `config.meta.format` | `"percent"` or `"currency"` |

```yaml
metrics:
  - name: us_orders
    label: "US Orders"
    description: "Count of orders from the United States."
    type: simple
    agg: count
    expr: 1
    filter: "{{ Dimension('order__country') }} = 'US'"   # top-level, native MetricFlow

  - name: return_rate
    label: "Return Rate"
    description: "Returned orders as a share of total orders."
    type: ratio
    numerator: returned_orders
    denominator: total_orders
    config:
      meta:
        format: "percent"   # config.meta only — not a native MetricFlow field
```

`filter:` uses `{{ Dimension('entity__col') }}` where `entity` is the entity name and `col` is the dimension name. dbt-cube-sync converts this to `${CUBE}.col` in the generated Cube.js `filters:` block. The `entity__` prefix is stripped automatically.

### Derived metrics in Format 3

Format 3 supports `type: derived` inline. Reference other metrics by name in `expr:`; list them under `input_metrics:`:

```yaml
metrics:
  - name: sessions
    label: "Sessions"
    description: "Total session count."
    type: simple
    agg: count
    expr: session_id

  - name: conversions
    label: "Conversions"
    description: "Sessions that resulted in a conversion."
    type: simple
    agg: sum
    expr: is_converted

  - name: conversion_rate
    label: "Conversion Rate"
    description: "Conversions divided by total sessions."
    type: derived
    expr: conversions / sessions
    input_metrics:
      - name: conversions
      - name: sessions
    config:
      meta:
        format: "percent"
```

For ratio metrics (a cleaner form of numerator ÷ denominator) use `type: ratio` with `numerator:` and `denominator:` referencing other metric names.
