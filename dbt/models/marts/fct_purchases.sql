select event_id, user_id, event_ts, event_date, country, platform, app_version, purchase_amount
from {{ ref('stg_game_events') }}
where event_name = 'purchase_completed'
