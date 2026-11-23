-- Silver must never contain events timestamped after their ingestion (+1h tolerance).
select event_id from {{ ref('stg_game_events') }}
where event_ts > {{ dbt.dateadd('hour', 1, 'ingested_at') }}
