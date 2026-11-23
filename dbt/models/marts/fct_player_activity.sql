{# Grain: one row per user per active day. #}
select
    e.user_id, e.event_date as activity_date,
    count(distinct e.session_id) as sessions,
    count(*) as events,
    sum(case when e.event_name = 'level_completed' then 1 else 0 end) as levels_completed,
    sum(case when e.event_name = 'level_failed' then 1 else 0 end) as levels_failed,
    sum(case when e.event_name = 'purchase_completed' then 1 else 0 end) as purchases,
    coalesce(sum(case when e.event_name = 'purchase_completed' then e.purchase_amount end), 0) as purchase_revenue,
    coalesce(sum(e.ad_revenue), 0) as ad_revenue
from {{ ref('stg_game_events') }} e
group by e.user_id, e.event_date
