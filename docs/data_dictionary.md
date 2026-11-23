# Data dictionary

Source of truth: [`storage/schemas/event_dictionary.yaml`](../storage/schemas/event_dictionary.yaml). It drives the ingestion contract (`ingestion/contracts.py`); dbt `accepted_values` tests mirror it. All data is simulated.

## Common fields (required on every event)
`event_id` · `event_name` · `user_id` · `session_id` · `event_timestamp` (ISO-8601 **with timezone**, stored UTC) · `country` (TR, DE, US, GB, FR, BR, IN, JP) · `platform` (Android, iOS) · `app_version` (`x.y.z`). Optional: `campaign_id` (absent = organic).

IDs match `^[A-Za-z0-9_-]{1,64}$`. Unknown fields are rejected (`extra="forbid"`).

## Events
| event_name | Required extra fields | Meaning |
|---|---|---|
| `app_open` | – | Player opened the game |
| `tutorial_started` | – | Tutorial began |
| `tutorial_completed` | `duration_seconds` | Tutorial finished |
| `level_started` | `level_id` (1–500) | Level attempt began |
| `level_completed` | `level_id`, `duration_seconds` | Level won |
| `level_failed` | `level_id`, `duration_seconds` | Level lost |
| `purchase_completed` | `purchase_amount` (USD, 0–1000, > 0) | In-app purchase |
| `ad_watched` | `ad_revenue` (USD, 0–10) | Ad impression revenue |

A field that is not listed for an event must be absent (`unexpected_field_for_event`).

## Quarantine reason codes
`invalid_payload` · `unknown_event_name` · `unknown_field:<f>` · `invalid_value:<f>` · `missing_required_field:<f>` · `unexpected_field_for_event:<f>`.
Silver-stage reasons (view `silver.stg_rejected_events`): `future_timestamp` · `unparsable_timestamp` · `duplicate_event_id` · `missing_purchase_amount`.

## Gold tables (grain)
| Table | Grain | Key metrics |
|---|---|---|
| `dim_users` | user | cohort_date, country, platform, install_version, campaign, tutorial_completed |
| `fct_player_activity` | user × day | sessions, events, levels, purchases, revenue |
| `mart_dau_wau_mau` | day | DAU, rolling WAU/MAU, stickiness, new vs returning |
| `mart_retention` | cohort × country × platform × tutorial × {1,7,30} | cohort_users, retained_users, retention (only matured cohorts) |
| `mart_funnel` | country × platform | per-user, order-aware step counts and conversions |
| `mart_level_dropoff` | level | users started/completed, fail rate, churned users |
| `mart_session_metrics` | day | sessions/user, avg duration, level completion rate |
| `mart_revenue` | day × country × platform | purchase + ad revenue, payers, ARPDAU |
| `mart_campaign_performance` | campaign | spend, CPI, cost per payer, payer conversion, ROAS |
| `mart_dq_event_volume` | day × version × event | event/user counts for DQ & anomaly checks |
