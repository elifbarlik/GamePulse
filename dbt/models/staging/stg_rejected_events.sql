{# Quarantine view: ingestion rejects + silver-level rejects. Nothing is silently dropped. #}
with parsed as (
    select *, {{ gp_parse_ts('event_timestamp') }} as event_ts,
           row_number() over (partition by event_id order by ingested_at, batch_id) as rn
    from {{ source('bronze', 'raw_game_events') }}
)
select 'silver' as stage, event_id, 'future_timestamp' as reason, ingested_at
from parsed where event_ts > {{ dbt.dateadd('hour', 1, 'ingested_at') }}
union all
select 'silver', event_id, 'unparsable_timestamp', ingested_at from parsed where event_ts is null
union all
select 'silver', event_id, 'duplicate_event_id', ingested_at from parsed where rn > 1
union all
select 'silver', event_id, 'missing_purchase_amount', ingested_at
from parsed where event_name = 'purchase_completed' and purchase_amount is null
union all
select 'ingestion', cast(null as {{ dbt.type_string() }}), reason, ingested_at
from {{ source('bronze', 'quarantine_events') }}
