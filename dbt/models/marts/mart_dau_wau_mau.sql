with days as (select date_day from {{ ref('dim_date') }}),
act as (select user_id, activity_date from {{ ref('fct_player_activity') }}),
rolling as (
    select d.date_day as activity_date,
        count(distinct case when a.activity_date = d.date_day then a.user_id end) as dau,
        count(distinct case when a.activity_date >= {{ gp_date_add_days('d.date_day', -6) }} then a.user_id end) as wau,
        count(distinct a.user_id) as mau
    from days d
    join act a on a.activity_date between {{ gp_date_add_days('d.date_day', -29) }} and d.date_day
    group by d.date_day
),
new_users as (
    select cohort_date as activity_date, count(*) as new_users from {{ ref('dim_users') }} group by cohort_date
)
select r.activity_date, r.dau, r.wau, r.mau,
    {{ gp_safe_divide('r.dau', 'r.mau') }} as stickiness,
    coalesce(n.new_users, 0) as new_users,
    r.dau - coalesce(n.new_users, 0) as returning_users,
    r.activity_date >= (select {{ gp_date_add_days('min(date_day)', 29) }} from days) as is_full_mau_window
from rolling r left join new_users n using (activity_date)
