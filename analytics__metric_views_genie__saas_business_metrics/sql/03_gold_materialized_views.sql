-- Gold layer: one daily core table and three thin roll-ups. Requires a serverless SQL warehouse
-- (create and refresh these materialized views from the same warehouse, see sql/09).
-- Order matters: customer_mrr_daily first, the others read it.
-- Date rules live in two places only:
--   * customer_mrr_daily covers the 24-month window start through YESTERDAY (current month to date included).
--   * the monthly roll-ups keep COMPLETE months only (through the last day of the previous month).
-- Opening-book events (signups before the window) are folded into the MRR balance on the first window day
-- and are not counted as new MRR.
-- After CREATE OR REPLACE: re-run sql/08 (column comments) and sql/05 (tags).

CREATE OR REPLACE MATERIALIZED VIEW saas_demo.gold.customer_mrr_daily
COMMENT 'Core fact: one row per customer per day the subscription was live, from the 24-month window start (or signup) through cancellation or yesterday, including the current month to date. closing_mrr is the end-of-day MRR balance (point-in-time, never sum across days), the other amounts are that day''s movements. Source of customer_mrr_monthly, customer_status_snapshot and revenue_daily_metrics.'
AS WITH b AS (SELECT add_months(trunc(current_date(),'MM'), -24) AS window_start, date_sub(current_date(), 1) AS data_end),
subs AS (
  SELECT c.customer_id, c.segment, c.region, p.plan_name AS plan, s.start_date, s.end_date
  FROM saas_demo.silver.customers c
  JOIN saas_demo.silver.subscriptions s USING (customer_id)
  JOIN saas_demo.silver.plans p USING (plan_id)
),
days AS (
  SELECT subs.customer_id, subs.segment, subs.region, subs.plan, x.date
  FROM subs CROSS JOIN b
  LATERAL VIEW explode(sequence(greatest(subs.start_date, b.window_start), coalesce(subs.end_date, b.data_end), INTERVAL 1 DAY)) x AS date
),
moves AS (
  SELECT e.customer_id, greatest(e.event_date, b.window_start) AS date,
    SUM(e.mrr_after - e.mrr_before) AS mrr_change,
    SUM(IF(e.event_date >= b.window_start AND e.event_type = 'new', e.mrr_after, 0)) AS new_mrr,
    SUM(IF(e.event_type = 'expansion', e.mrr_after - e.mrr_before, 0)) AS expansion_mrr,
    SUM(IF(e.event_type = 'contraction', e.mrr_before - e.mrr_after, 0)) AS contraction_mrr,
    SUM(IF(e.event_type = 'churn', e.mrr_before, 0)) AS churned_mrr,
    COUNT_IF(e.event_date >= b.window_start AND e.event_type = 'new') AS new_customers,
    COUNT_IF(e.event_type = 'churn') AS churned_customers
  FROM saas_demo.silver.mrr_events e CROSS JOIN b
  WHERE e.event_date <= b.data_end
  GROUP BY ALL
),
balance AS (
  SELECT d.*, coalesce(m.new_mrr, 0) AS new_mrr, coalesce(m.expansion_mrr, 0) AS expansion_mrr,
    coalesce(m.contraction_mrr, 0) AS contraction_mrr, coalesce(m.churned_mrr, 0) AS churned_mrr,
    coalesce(m.new_customers, 0) AS new_customers, coalesce(m.churned_customers, 0) AS churned_customers,
    SUM(coalesce(m.mrr_change, 0)) OVER (PARTITION BY d.customer_id ORDER BY d.date) AS closing_mrr
  FROM days d LEFT JOIN moves m USING (customer_id, date)
)
SELECT date, customer_id, segment, region, plan,
  CAST(closing_mrr AS DECIMAL(14,2)) AS closing_mrr,
  CAST(IF(closing_mrr > 0, 1, 0) AS INT) AS is_active,
  CAST(new_mrr AS DECIMAL(14,2)) AS new_mrr,
  CAST(expansion_mrr AS DECIMAL(14,2)) AS expansion_mrr,
  CAST(contraction_mrr AS DECIMAL(14,2)) AS contraction_mrr,
  CAST(churned_mrr AS DECIMAL(14,2)) AS churned_mrr,
  CAST(new_customers AS INT) AS new_customers,
  CAST(churned_customers AS INT) AS churned_customers,
  CAST(closing_mrr / day(last_day(date)) AS DECIMAL(18,6)) AS recognized_revenue
FROM balance;

CREATE OR REPLACE MATERIALIZED VIEW saas_demo.gold.customer_mrr_monthly
COMMENT 'Customer x month MRR waterfall (USD) for the 24 complete months before today, rolled up from customer_mrr_daily. closing_mrr = month-end balance, opening_mrr = closing_mrr - (new + expansion - contraction - churned). Point-in-time balances are never summed across months. Source of revenue_monthly_metrics.'
AS WITH b AS (SELECT date_sub(trunc(current_date(),'MM'), 1) AS last_complete_day),
m AS (
  SELECT trunc(date, 'MM') AS month, customer_id, segment, region, plan,
    max_by(closing_mrr, date) AS closing_mrr,
    SUM(new_mrr) AS new_mrr, SUM(expansion_mrr) AS expansion_mrr,
    SUM(contraction_mrr) AS contraction_mrr, SUM(churned_mrr) AS churned_mrr,
    SUM(churned_customers) AS churned_customers
  FROM saas_demo.gold.customer_mrr_daily CROSS JOIN b
  WHERE date <= b.last_complete_day
  GROUP BY ALL
)
SELECT month, customer_id, segment, region, plan,
  CAST(closing_mrr - (new_mrr + expansion_mrr - contraction_mrr - churned_mrr) AS DECIMAL(14,2)) AS opening_mrr,
  CAST(new_mrr AS DECIMAL(14,2)) AS new_mrr, CAST(expansion_mrr AS DECIMAL(14,2)) AS expansion_mrr,
  CAST(contraction_mrr AS DECIMAL(14,2)) AS contraction_mrr, CAST(churned_mrr AS DECIMAL(14,2)) AS churned_mrr,
  CAST(closing_mrr AS DECIMAL(14,2)) AS closing_mrr,
  CAST(IF(closing_mrr - (new_mrr + expansion_mrr - contraction_mrr - churned_mrr) > 0, 1, 0) AS INT) AS opening_customers,
  CAST(churned_customers AS INT) AS churned_customers
FROM m;

CREATE OR REPLACE MATERIALIZED VIEW saas_demo.gold.customer_status_snapshot
COMMENT 'One row per customer as of the end of the last complete month: current MRR (0 if churned), tenure, status and churn month. Customers who signed up in the current month are not included yet. Source of customer_health_metrics.'
AS WITH b AS (SELECT date_sub(trunc(current_date(),'MM'), 1) AS last_complete_day),
latest AS (
  SELECT customer_id, max_by(closing_mrr, date) AS closing_mrr
  FROM saas_demo.gold.customer_mrr_daily CROSS JOIN b
  WHERE date <= b.last_complete_day
  GROUP BY customer_id
)
SELECT c.customer_id, c.company_name, c.segment, c.region, p.plan_name AS plan, c.signup_date,
  CAST(coalesce(l.closing_mrr, 0) AS DECIMAL(14,2)) AS current_mrr,
  CAST(floor(months_between(least(coalesce(s.end_date, b.last_complete_day), b.last_complete_day), c.signup_date)) AS INT) AS tenure_months,
  IF(s.end_date <= b.last_complete_day, 'churned', 'active') AS status,
  IF(s.end_date <= b.last_complete_day, trunc(s.end_date, 'MM'), NULL) AS churn_month
FROM saas_demo.silver.customers c
JOIN saas_demo.silver.subscriptions s USING (customer_id)
JOIN saas_demo.silver.plans p USING (plan_id)
LEFT JOIN latest l USING (customer_id)
CROSS JOIN b
WHERE c.signup_date <= b.last_complete_day;

CREATE OR REPLACE MATERIALIZED VIEW saas_demo.gold.signup_cohort_retention_monthly
COMMENT 'Signup-month cohorts x months since signup (cohorts inside the 24-month window, complete months only). Logo retention = customers_active / customers_start, revenue retention = mrr_now / mrr_start. Do not sum rows within a cohort.'
AS WITH cohort AS (
  SELECT customer_id, month AS signup_month
  FROM saas_demo.gold.customer_mrr_monthly
  WHERE new_mrr > 0
),
grid AS (
  SELECT c.signup_month, CAST(months_between(m.month, c.signup_month) AS INT) AS months_since_signup, m.closing_mrr
  FROM cohort c JOIN saas_demo.gold.customer_mrr_monthly m USING (customer_id)
),
start AS (
  SELECT signup_month, COUNT(*) AS customers_start, SUM(closing_mrr) AS mrr_start
  FROM grid WHERE months_since_signup = 0 GROUP BY signup_month
),
offsets AS (
  SELECT s.*, k AS months_since_signup
  FROM start s
  LATERAL VIEW explode(sequence(0, CAST(months_between(add_months(trunc(current_date(),'MM'), -1), s.signup_month) AS INT))) x AS k
),
active AS (
  SELECT signup_month, months_since_signup, COUNT_IF(closing_mrr > 0) AS customers_active, SUM(closing_mrr) AS mrr_now
  FROM grid GROUP BY ALL
)
SELECT o.signup_month, o.months_since_signup,
  CAST(o.customers_start AS INT) AS customers_start, CAST(coalesce(a.customers_active, 0) AS INT) AS customers_active,
  CAST(o.mrr_start AS DECIMAL(14,2)) AS mrr_start, CAST(coalesce(a.mrr_now, 0) AS DECIMAL(14,2)) AS mrr_now
FROM offsets o LEFT JOIN active a USING (signup_month, months_since_signup)
