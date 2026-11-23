{# Feeds data-quality volume checks and anomaly detection: per day x app_version x event. #}
select event_date, app_version, event_name,
       count(*) as events, count(distinct user_id) as users
from {{ ref('stg_game_events') }}
group by event_date, app_version, event_name
