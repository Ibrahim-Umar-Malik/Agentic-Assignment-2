-- Hospital KPI reporting
-- model: fct_hospital_kpi
with base as (
  select * from {{ ref('stg_events') }}
)
select date_trunc('week', event_ts) as week, count(distinct user_id) as active_users
from base
group by 1
