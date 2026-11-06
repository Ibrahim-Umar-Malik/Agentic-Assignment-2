-- Executive sales dashboard in Power BI
-- model: fct_sales_dashboard
with base as (
  select * from {{ ref('stg_events') }}
)
select date_trunc('week', event_ts) as week, count(distinct user_id) as active_users
from base
group by 1
