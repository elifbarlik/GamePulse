with s as (
    select
        session_id, user_id,
        min(event_ts) as session_start, max(event_ts) as session_end,
        min(event_date) as session_date,
        count(*) as n_events,
        sum(case when event_name = 'level_started' then 1 else 0 end) as levels_started,
        sum(case when event_name = 'level_completed' then 1 else 0 end) as levels_completed,
        sum(case when event_name = 'level_failed' then 1 else 0 end) as levels_failed,
        min(country) as country, min(platform) as platform, min(app_version) as app_version
    from {{ ref('stg_game_events') }}
    group by session_id, user_id
),
seq as (
    select *,
        row_number() over (partition by user_id order by session_start) as session_number,
        lag(session_date) over (partition by user_id order by session_start) as prev_session_date
    from s
)
select
    *,
    {{ dbt.datediff('session_start', 'session_end', 'second') }} as duration_seconds,
    {{ dbt.datediff('prev_session_date', 'session_date', 'day') }} as days_since_prev_session
from seq
