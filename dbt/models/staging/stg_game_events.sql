{{ config(
    materialized='incremental',
    unique_key='event_id',
    incremental_strategy=gp_incremental_strategy(),
    partition_by=({'field': 'event_date', 'data_type': 'date'} if target.type == 'bigquery' else none),
    cluster_by=(['user_id', 'event_name'] if target.type == 'bigquery' else none)
) }}

{# Silver: parsed, valid, de-duplicated events. Incremental on ingested_at; upsert on event_id. #}
with src as (
    select *, {{ gp_parse_ts('event_timestamp') }} as event_ts
    from {{ source('bronze', 'raw_game_events') }}
    {% if is_incremental() %}
    where ingested_at > (select coalesce(max(ingested_at), cast('1970-01-01' as timestamp)) from {{ this }})
    {% endif %}
),
valid as (
    select * from src
    where event_ts is not null
      and user_id is not null
      and event_ts <= {{ dbt.dateadd('hour', 1, 'ingested_at') }}
      and not (event_name = 'purchase_completed' and purchase_amount is null)
),
dedup as (
    select *, row_number() over (partition by event_id order by ingested_at, batch_id) as rn
    from valid
)
select
    event_id, event_name, user_id, session_id, event_ts,
    cast(event_ts as date) as event_date,
    country, platform, app_version, campaign_id,
    level_id, duration_seconds, purchase_amount, ad_revenue,
    batch_id, ingested_at
from dedup
where rn = 1
