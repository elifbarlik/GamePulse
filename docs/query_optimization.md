# Query optimisation

## Measured (DuckDB, local, 2.49 M events, median of 5 runs)
Same question — **D1 retention per cohort** — answered at three layers (`python -m analytics.benchmark`):

| Layer | Rows scanned | Median time | Why |
|---|---|---|---|
| Bronze (raw strings) | 2,487,517 | 139.9 ms | parses ISO strings, scans every event, de-dup not applied |
| Silver (`stg_game_events`) | 2,472,591 | 49.8 ms | typed `event_date`, duplicates/invalid removed |
| Gold (`mart_retention`) | 3,826 | **2.4 ms** | pre-aggregated at cohort × segment grain |

≈ **58× faster** than raw, with ~650× fewer rows. Gold is computed once per run, so every dashboard query is cheap.

## BigQuery (configured, not benchmarked here)
`stg_game_events` is created with
```
partition_by = event_date (DATE)      cluster_by = [user_id, event_name]
```
(see `dbt/models/staging/stg_game_events.sql`). Expected effect: date-range filters prune partitions (billed bytes ∝ days scanned) and `WHERE event_name = …` / per-user joins read fewer blocks thanks to clustering. To measure on your project:
```sql
-- dry run shows bytes processed without cost
bq query --dry_run --use_legacy_sql=false 'SELECT COUNT(*) FROM silver.stg_game_events WHERE event_date BETWEEN "2026-10-01" AND "2026-10-07" AND event_name="app_open"'
```
Compare against the same table created without partition/cluster and record both numbers here.

## Modelling choices that reduce work
* `fct_player_activity` (user × day) is the single base for DAU/WAU/MAU, retention and revenue — marts never re-scan raw events.
* Rolling MAU uses a bounded date join (`between d-29 and d`) instead of a correlated sub-query.
* `COUNTIF` is avoided in favour of `SUM(CASE …)` so one SQL works on DuckDB and BigQuery.
* Incremental Silver processes only batches with `ingested_at` newer than the table's high-water mark.
