-- dbt and Snowflake analytics warehouse
-- model: fct_dbt_warehouse
with base as (
  select * from {{ ref('stg_events') }}
)
select date_trunc('week', event_ts) as week, count(distinct user_id) as active_users
from base
group by 1
