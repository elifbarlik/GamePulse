with ranked as (
    select *, row_number() over (partition by user_id order by event_ts, event_id) as rn
    from {{ ref('stg_game_events') }}
),
first_ev as (
    select user_id, event_date as cohort_date, country, platform,
           app_version as install_version, campaign_id
    from ranked where rn = 1
),
flags as (
    select user_id,
        max(case when event_name = 'tutorial_completed' then 1 else 0 end) = 1 as tutorial_completed,
        min(case when event_name = 'purchase_completed' then event_date end) as first_purchase_date
    from {{ ref('stg_game_events') }}
    group by user_id
)
select f.*, fl.tutorial_completed, fl.first_purchase_date,
       coalesce(f.campaign_id, 'organic') as acquisition_source
from first_ev f join flags fl using (user_id)
