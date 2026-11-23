-- A later funnel step can never have more users than the previous one.
select * from {{ ref('mart_funnel') }}
where tutorial_started_users > app_open_users
   or tutorial_completed_users > tutorial_started_users
   or level_1_completed_users > tutorial_completed_users
   or purchase_users > level_1_completed_users
