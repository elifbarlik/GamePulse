# Query optimisation

## Measured (DuckDB, local, 2.49 M events, median of 5 runs)
Same question — **D1 retention per cohort** — answered at three layers (`python -m analytics.benchmark`):

| Layer | Rows scanned | Median time | Why |
|---|---|---|---|
| Bronze (raw strings) | 2,487,517 | 139.9 ms | parses ISO strings, scans every event, de-dup not applied |
| Silver (`stg_game_events`) | 2,472,591 | 49.8 ms | typed `event_date`, duplicates/invalid removed |
| Gold (`mart_retention`) | 3,826 | **2.4 ms** | pre-aggregated at cohort × segment grain |

≈ **58× faster** than raw, with ~650× fewer rows. Gold is computed once per run, so every dashboard query is cheap.

## BigQuery (live project, Sandbox)
Measured from the `dbt build` log and the console on the same 2.49 M-event dataset:

| Step | Bytes processed |
|---|---|
| Build `silver.stg_game_events` from Bronze (one-off, per run) | 367.4 MiB |
| Read `silver.stg_game_events` to build one mart (typical) | 97–197 MiB |
| `SELECT day_n, retention … FROM gold.mart_retention` (what a dashboard runs) | **89.67 KB** |

A dashboard query on Gold reads roughly **1,000–2,000× less** than a mart build from Silver (97–197 MiB vs 89.67 KB) — the Gold layer is what keeps BI cost flat. I did not benchmark the same question against the raw Bronze table, nor Silver with vs. without partitioning, so no claim is made about partition/cluster savings; `stg_game_events` is configured with
```
partition_by = event_date (DATE)      cluster_by = [user_id, event_name]
```
(see `dbt/models/staging/stg_game_events.sql`). In Sandbox mode (`GP_BQ_SANDBOX=1`) Silver is a plain table, and partition/cluster options apply at creation. To measure the effect yourself: `bq query --dry_run --use_legacy_sql=false '<query>'` against a partitioned and an unpartitioned copy.

## Modelling choices that reduce work
* `fct_player_activity` (user × day) is the single base for DAU/WAU/MAU, retention and revenue — marts never re-scan raw events.
* Rolling MAU uses a bounded date join (`between d-29 and d`) instead of a correlated sub-query.
* `COUNTIF` is avoided in favour of `SUM(CASE …)` so one SQL works on DuckDB and BigQuery.
* Incremental Silver processes only batches with `ingested_at` newer than the table's high-water mark.
