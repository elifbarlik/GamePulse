select
    s.session_date as activity_date,
    count(*) as sessions,
    count(distinct s.user_id) as active_users,
    avg(s.duration_seconds) as avg_session_seconds,
    {{ gp_safe_divide('count(*)', 'count(distinct s.user_id)') }} as sessions_per_user,
    sum(s.levels_completed) as levels_completed,
    sum(s.levels_failed) as levels_failed,
    {{ gp_safe_divide('sum(s.levels_completed)', 'sum(s.levels_completed) + sum(s.levels_failed)') }} as level_completion_rate,
    {{ gp_safe_divide('sum(s.levels_completed)', 'count(distinct s.user_id)') }} as levels_completed_per_active_user
from {{ ref('int_player_sessions') }} s
group by s.session_date
