select * from {{ ref('mart_retention') }}
where retention < 0 or retention > 1 or retained_users > cohort_users
