select distinct
    event_date as date_day,
    {{ dbt.date_trunc('week', 'event_date') }} as week_start,
    {{ dbt.date_trunc('month', 'event_date') }} as month_start
from {{ ref('stg_game_events') }}
