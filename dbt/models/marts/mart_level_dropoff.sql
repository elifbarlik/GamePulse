with per_user_level as (
    select user_id, level_id,
        sum(case when event_name = 'level_started' then 1 else 0 end) as starts,
        sum(case when event_name = 'level_completed' then 1 else 0 end) as completes,
        sum(case when event_name = 'level_failed' then 1 else 0 end) as fails
    from {{ ref('stg_game_events') }}
    where level_id is not null
    group by user_id, level_id
),
user_last as (
    select user_id, max(level_id) as max_level, max(event_date) as last_active
    from {{ ref('stg_game_events') }} where level_id is not null group by user_id
),
horizon as (select max(activity_date) as d from {{ ref('fct_player_activity') }})
select
    p.level_id,
    count(*) as users_started,
    sum(case when p.completes > 0 then 1 else 0 end) as users_completed,
    sum(p.fails) as total_fails,
    sum(p.starts) as total_attempts,
    {{ gp_safe_divide('sum(case when p.completes > 0 then 1 else 0 end)', 'count(*)') }} as completion_rate,
    {{ gp_safe_divide('sum(p.fails)', 'sum(p.starts)') }} as fail_rate,
    {# churned: last level reached and inactive for 7+ days #}
    sum(case when ul.max_level = p.level_id
              and ul.last_active <= {{ dbt.dateadd('day', -7, 'h.d') }} then 1 else 0 end) as churned_users
from per_user_level p
join user_last ul using (user_id)
cross join horizon h
group by p.level_id
