-- Silver must never contain events timestamped after their ingestion (+1h tolerance).
select event_id from {{ ref('stg_game_events') }}
where event_ts > {{ gp_hour_after('ingested_at') }}
