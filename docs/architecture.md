# Architecture

> All data is **simulated** (seeded Python generator). Nothing here is real company or player data.

```mermaid
flowchart LR
  subgraph Sources
    SIM[Event simulator<br/>2.5M events / 50k players<br/>+ injected defects]
    CAMP[campaigns.csv]
  end
  subgraph Ingestion
    API[FastAPI /v1/events<br/>API key, rate limit, size limit]
    BATCH[Batch loader<br/>content-hash batch_id]
    STREAM[Redpanda → consumer<br/>offset-range batch_id]
    CONTRACT{{Pydantic + event dictionary<br/>contract}}
  end
  subgraph Bronze["Bronze (immutable, append-only)"]
    RAW[(raw_game_events)]
    QUAR[(quarantine_events<br/>reason codes)]
    LEDGER[(ingestion_batches<br/>idempotency ledger)]
  end
  subgraph Silver["Silver (dbt)"]
    STG[stg_game_events<br/>incremental, dedup, typed]
    REJ[stg_rejected_events]
    SESS[int_player_sessions<br/>LAG sessionization]
  end
  DQ{{DQ gate<br/>freshness · completeness · volume<br/>tracking coverage · anomaly}}
  subgraph Gold["Gold (dbt marts)"]
    DIM[dim_users · dim_date · dim_campaign]
    FCT[fct_player_activity · fct_purchases]
    MART[mart_dau_wau_mau · mart_retention<br/>mart_funnel · mart_level_dropoff<br/>mart_session_metrics · mart_revenue<br/>mart_campaign_performance]
  end
  SIM --> API & BATCH & STREAM
  CAMP --> BATCH
  API & BATCH & STREAM --> CONTRACT
  CONTRACT -->|valid| RAW
  CONTRACT -->|invalid| QUAR
  CONTRACT --> LEDGER
  RAW --> STG --> SESS
  RAW --> REJ
  STG --> DQ -->|pass| DIM --> FCT --> MART
  DQ -.->|critical fail: Gold build skipped| ALERT[Webhook alert]
  MART --> REPORT[Dashboards PNG / Looker Studio]
  MART --> ASSIST[KPI assistant<br/>allowlisted SQL only]
  API --> PROM[(Prometheus)] --> GRAF[Grafana]
  STREAM --> PROM
```

## Layers
| Layer | Contents | Guarantees |
|---|---|---|
| Bronze | Events that passed the structural contract, plus quarantined payloads with reason codes | Never mutated; every row has `batch_id`, `source_file`, `ingested_at` |
| Silver | Typed, deduplicated events; rejected-event view; sessions | `event_id` unique; no future timestamps; purchases always have an amount |
| Gold | Star-schema dims/facts and KPI marts | Built only if the DQ gate has no critical failure |

## Lineage (dbt)
```
bronze.raw_game_events ─▶ stg_game_events ─▶ int_player_sessions ─▶ mart_session_metrics
                                   │
                                   ├─▶ dim_users ─┬─▶ mart_retention
                                   │              ├─▶ mart_funnel
                                   │              └─▶ mart_campaign_performance ◀─ dim_campaign ◀─ stg_campaigns ◀─ bronze.raw_campaigns
                                   ├─▶ fct_player_activity ─▶ mart_dau_wau_mau, mart_revenue, mart_retention
                                   ├─▶ mart_level_dropoff · fct_purchases · dim_date · mart_dq_event_volume
bronze.raw_game_events + bronze.quarantine_events ─▶ stg_rejected_events
```
`dbt docs generate && dbt docs serve --project-dir dbt --profiles-dir dbt` renders the interactive lineage graph.

## Idempotency
* **Batch level:** `batch_id` is a content hash (API/batch loader) or `topic_partition_firstOffset_lastOffset` (consumer). A batch is recorded in `ingestion_batches` in the same transaction as its rows; re-ingesting is a no-op.
* **Event level:** Silver deduplicates on `event_id` (`ROW_NUMBER`) and the incremental model upserts (`delete+insert` on DuckDB, `merge` on BigQuery), so late duplicates never double-count.
* **Delivery:** Kafka offsets are committed *after* the Bronze write (at-least-once) — replays are absorbed by the ledger.

## Storage backends
| | Local (default, free) | Cloud |
|---|---|---|
| Warehouse | DuckDB + `dbt-duckdb` | BigQuery + `dbt-bigquery` (same models; dialect differences isolated in `dbt/macros/gp_macros.sql`; BigQuery partition by `event_date`, cluster by `user_id, event_name`) |
| Ingestion store | `ingestion/store.py` | `storage/bigquery.py` (batch load jobs only — works without streaming inserts/billing) |

## Design decisions & trade-offs
* **DuckDB locally, BigQuery for cloud:** zero cost and a fast test loop; the same dbt models target both.
* **Reject at the door *and* in Silver:** structural errors (unknown event, missing required field) are quarantined at ingestion; time-dependent/cross-row errors (future timestamp, duplicates) need Silver context.
* **No Great Expectations/Soda:** dbt tests + a ~100-line DQ module cover the same rules with less to maintain.
* **Rule-based assistant instead of an LLM:** no cost, no prompt-injection surface; an LLM could later act only as a router over the same allowlist.
