# Data quality framework

Three lines of defence, cheapest first:

1. **Contract at ingestion** (`ingestion/contracts.py`) – structure, types, enums, required fields per event. Failures → `bronze.quarantine_events` with a reason code; nothing is lost.
2. **dbt tests** – `unique`, `not_null`, `accepted_values`, `relationships` and singular tests (`assert_no_future_events`, `assert_purchase_has_amount`, `assert_retention_valid`, `assert_funnel_monotonic`).
3. **Run-time DQ gate** (`analytics/dq/checks.py`, run between Silver and Gold) – results persisted to `gold.dq_results`.

| Check | Severity | Rule |
|---|---|---|
| `freshness` | critical | last ingestion ≤ 24 h ago |
| `reject_ratio` | critical | rejected events ≤ 10 % of all received |
| `completeness` | critical | no Silver row misses a field its event requires |
| `version_event_coverage` | warning | each app version with traffic must emit `level_completed` (≥ 20 % of `level_started`) — catches tracking regressions |
| `daily_volume` | warning | day-over-day **log-change** z-score (14-day window) must not drop below −3 |
| `dau_drop` | warning | DAU/volume drop classified as `pipeline_issue` vs `real_user_loss` |

**Critical failure ⇒ exit code 2 ⇒ Gold is not rebuilt** (Airflow: `data_quality_gate` fails with `retries=0`, so `dbt_gold` never runs). Warnings are alerted (webhook, `https` only) but do not block.
Quality score = share of checks passed, critical weighted ×3.

## Why change-based z-scores
Comparing a day to the trailing *level* mean flags every day of a natural decline (the simulated audience decays after installs stop). Using the z-score of the day-over-day log change ignores smooth trends and reacts to sudden breaks. A drop must also be ≥ 10 % vs the previous day to be reported (avoids alarms on near-zero-variance series).

## `pipeline_issue` vs `real_user_loss`
* events **and** events-per-active-user collapse together → data went missing / tracking broke → `pipeline_issue`
* DAU falls while events-per-user stays normal → the audience really shrank → `real_user_loss`

## Result on the simulated dataset (known ground truth in `data/raw/scenarios.json`)
| Injected scenario | Detected by |
|---|---|
| v1.4.2 never sends `level_completed` (1–12 Oct) | `version_event_coverage` fails for 1.4.2; 1 Oct flagged `pipeline_issue` |
| 75 % of events dropped on 21 Oct (observed −77 % day-over-day) | `daily_volume` + `dau_drop` → `pipeline_issue` (z_events ≈ −21) |
| ~1.5 % corrupt events (duplicates, future timestamps, null user, purchase w/o amount, unknown event) | quarantine / Silver rejection; never reach Gold |

Also reported: 16 and 18 Oct as `real_user_loss` (z_dau ≈ −3…−5). That is a *correct* verdict — simulated installs stop on 15 Oct, so the audience genuinely shrinks while events-per-user stays normal. Thresholds are configurable; on a different series expect to tune `z_threshold` / `min_drop`.
