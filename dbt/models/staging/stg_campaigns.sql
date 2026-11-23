select campaign_id, country, spend, installs from {{ source('bronze', 'raw_campaigns') }}
