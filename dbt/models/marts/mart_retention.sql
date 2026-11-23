{# D1 / D7 / D30 classic retention by cohort. Only matured cohorts (cohort_date + N <= last data day). #}
with horizons as (select 1 as day_n union all select 7 union all select 30),
last_day as (select max(activity_date) as d from {{ ref('fct_player_activity') }}),
cohort as (
    select u.user_id, u.cohort_date, u.country, u.platform, u.tutorial_completed, h.day_n
    from {{ ref('dim_users') }} u cross join horizons h cross join last_day l
    where {{ gp_date_add_days('u.cohort_date', 'h.day_n') }} <= l.d
)
select
    c.cohort_date, c.country, c.platform, c.tutorial_completed, c.day_n,
    count(distinct c.user_id) as cohort_users,
    count(distinct a.user_id) as retained_users,
    {{ gp_safe_divide('count(distinct a.user_id)', 'count(distinct c.user_id)') }} as retention
from cohort c
left join {{ ref('fct_player_activity') }} a
    on a.user_id = c.user_id and a.activity_date = {{ gp_date_add_days('c.cohort_date', 'c.day_n') }}
group by c.cohort_date, c.country, c.platform, c.tutorial_completed, c.day_n
