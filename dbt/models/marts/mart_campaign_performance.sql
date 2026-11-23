with user_rev as (
    select u.campaign_id, u.user_id,
        sum(f.purchase_revenue) as purchase_revenue, sum(f.ad_revenue) as ad_revenue,
        sum(f.purchases) as purchases
    from {{ ref('dim_users') }} u
    join {{ ref('fct_player_activity') }} f using (user_id)
    where u.campaign_id is not null
    group by u.campaign_id, u.user_id
),
agg as (
    select campaign_id, count(*) as attributed_users,
        sum(case when purchases > 0 then 1 else 0 end) as paying_users,
        sum(purchase_revenue + ad_revenue) as revenue
    from user_rev group by campaign_id
)
select c.campaign_id, c.country, c.spend, c.installs as reported_installs,
    coalesce(a.attributed_users, 0) as attributed_users,
    coalesce(a.paying_users, 0) as paying_users,
    coalesce(a.revenue, 0) as revenue,
    {{ gp_safe_divide('c.spend', 'c.installs') }} as cpi,
    {{ gp_safe_divide('c.spend', 'a.paying_users') }} as cost_per_paying_user,
    {{ gp_safe_divide('a.paying_users', 'a.attributed_users') }} as payer_conversion,
    {{ gp_safe_divide('a.revenue', 'c.spend') }} as roas
from {{ ref('dim_campaign') }} c left join agg a using (campaign_id)
