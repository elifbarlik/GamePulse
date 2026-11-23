select
    f.activity_date, u.country, u.platform,
    sum(f.purchase_revenue) as purchase_revenue,
    sum(f.ad_revenue) as ad_revenue,
    sum(f.purchases) as purchases,
    count(distinct case when f.purchases > 0 then f.user_id end) as paying_users,
    count(distinct f.user_id) as dau,
    {{ gp_safe_divide('sum(f.purchase_revenue) + sum(f.ad_revenue)', 'count(distinct f.user_id)') }} as arpdau
from {{ ref('fct_player_activity') }} f
join {{ ref('dim_users') }} u using (user_id)
group by f.activity_date, u.country, u.platform
