select campaign_id, country, spend, installs from {{ ref('stg_campaigns') }}
