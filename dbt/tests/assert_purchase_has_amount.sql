-- purchase_completed without purchase_amount must never reach Silver/Gold.
select event_id from {{ ref('stg_game_events') }}
where event_name = 'purchase_completed' and (purchase_amount is null or purchase_amount <= 0)
