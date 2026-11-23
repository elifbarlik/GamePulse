{# Per-user, order-aware funnel: each step must happen at/after the previous step's first occurrence. #}
with steps as (
    select user_id,
        min(case when event_name = 'app_open' then event_ts end) as t_open,
        min(case when event_name = 'tutorial_started' then event_ts end) as t_tut_start,
        min(case when event_name = 'tutorial_completed' then event_ts end) as t_tut_done,
        min(case when event_name = 'level_completed' and level_id = 1 then event_ts end) as t_lvl1,
        min(case when event_name = 'purchase_completed' then event_ts end) as t_purchase
    from {{ ref('stg_game_events') }}
    group by user_id
),
flags as (
    select user_id,
        coalesce(t_open is not null, false) as s1,
        coalesce(t_tut_start >= t_open, false) as s2,
        coalesce(t_tut_done >= t_tut_start and t_tut_start >= t_open, false) as s3,
        coalesce(t_lvl1 >= t_tut_done and t_tut_done >= t_tut_start and t_tut_start >= t_open, false) as s4,
        coalesce(t_purchase >= t_lvl1 and t_lvl1 >= t_tut_done and t_tut_done >= t_tut_start
                 and t_tut_start >= t_open, false) as s5
    from steps
)
select
    u.country, u.platform,
    sum(case when f.s1 then 1 else 0 end) as app_open_users,
    sum(case when f.s2 then 1 else 0 end) as tutorial_started_users,
    sum(case when f.s3 then 1 else 0 end) as tutorial_completed_users,
    sum(case when f.s4 then 1 else 0 end) as level_1_completed_users,
    sum(case when f.s5 then 1 else 0 end) as purchase_users,
    {{ gp_safe_divide('sum(case when f.s2 then 1 else 0 end)', 'sum(case when f.s1 then 1 else 0 end)') }} as conv_open_to_tut_start,
    {{ gp_safe_divide('sum(case when f.s3 then 1 else 0 end)', 'sum(case when f.s2 then 1 else 0 end)') }} as conv_tut_start_to_done,
    {{ gp_safe_divide('sum(case when f.s4 then 1 else 0 end)', 'sum(case when f.s3 then 1 else 0 end)') }} as conv_tut_done_to_lvl1,
    {{ gp_safe_divide('sum(case when f.s5 then 1 else 0 end)', 'sum(case when f.s4 then 1 else 0 end)') }} as conv_lvl1_to_purchase
from flags f join {{ ref('dim_users') }} u using (user_id)
group by u.country, u.platform
