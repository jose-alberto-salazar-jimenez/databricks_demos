-- Exported from the live workspace with SHOW CREATE TABLE. Requires a serverless SQL warehouse.
-- Order matters: customer_snapshot and cohort_retention read mrr_monthly.
-- mrr_monthly folds pre-window 'new' events (opening book) into the opening MRR of the first window month.
-- After CREATE OR REPLACE: re-run sql/08 (column comments) and sql/05 (tags).
-- Refresh monthly (window is based on current_date()): REFRESH MATERIALIZED VIEW <name>

CREATE OR REPLACE MATERIALIZED VIEW `saas_demo`.`gold`.`mrr_monthly` (
  month DATE COMMENT 'First day of the calendar month. Together with customer_id forms the unique key.',
  customer_id STRING COLLATE UTF8_BINARY COMMENT 'Customer key. Joins to customer_snapshot and the silver tables.',
  segment STRING COLLATE UTF8_BINARY COMMENT 'Customer size segment (SMB, Mid-Market, Enterprise), from customers.',
  region STRING COLLATE UTF8_BINARY COMMENT 'Sales region (NA, EMEA, APAC, LATAM), from customers.',
  plan STRING COLLATE UTF8_BINARY COMMENT 'Plan tier of the customer subscription (Starter, Pro, Enterprise).',
  opening_mrr DECIMAL(14,2) COMMENT 'MRR at the start of the month in USD (equals previous closing). For opening-book customers the first window month opens with their existing MRR.',
  new_mrr DECIMAL(14,2) COMMENT 'MRR from a first subscription signed inside the window. Only in the signup month, otherwise 0.',
  expansion_mrr DECIMAL(14,2) COMMENT 'MRR increases during the month in USD, otherwise 0.',
  contraction_mrr DECIMAL(14,2) COMMENT 'MRR decreases while the customer stays, positive number in USD.',
  churned_mrr DECIMAL(14,2) COMMENT 'MRR lost when the customer cancelled, positive number in USD. Only in the churn month.',
  closing_mrr DECIMAL(14,2) COMMENT 'MRR at the end of the month in USD. 0 in the churn month. Point-in-time: never sum across months.',
  opening_customers INT COMMENT '1 if the customer had MRR at the start of the month, else 0. Sum = customers at month start.',
  churned_customers INT COMMENT '1 if the customer cancelled in this month, else 0.')
COMMENT 'Customer x month MRR waterfall (USD) for the 24 complete months before the build date. closing_mrr = opening + new + expansion - contraction - churned. Rows from the first window month (or signup month) through the churn month or last complete month. Source of saas_revenue_metrics.'
AS WITH b AS (SELECT date_sub(trunc(current_date(),'MM'), 1) AS we, add_months(trunc(current_date(),'MM'), -24) AS ws),
cust AS (
  SELECT c.customer_id, c.segment, c.region, p.plan_name AS plan, s.start_date, s.end_date
  FROM saas_demo.silver.customers c
  JOIN saas_demo.silver.subscriptions s USING (customer_id)
  JOIN saas_demo.silver.plans p USING (plan_id)
),
spine AS (
  SELECT cust.*, m AS month
  FROM cust CROSS JOIN b
  LATERAL VIEW explode(sequence(greatest(trunc(start_date,'MM'), b.ws), trunc(coalesce(end_date, b.we),'MM'), INTERVAL 1 MONTH)) e AS m
),
ev AS (
  SELECT e.customer_id, greatest(trunc(e.event_date,'MM'), b.ws) AS month,
    SUM(CASE WHEN e.event_date < b.ws THEN e.mrr_after - e.mrr_before ELSE 0 END) AS opening_book_mrr,
    SUM(CASE WHEN e.event_date >= b.ws AND e.event_type='new' THEN e.mrr_after - e.mrr_before ELSE 0 END) AS new_mrr,
    SUM(CASE WHEN e.event_date >= b.ws AND e.event_type='expansion' THEN e.mrr_after - e.mrr_before ELSE 0 END) AS expansion_mrr,
    SUM(CASE WHEN e.event_date >= b.ws AND e.event_type='contraction' THEN e.mrr_before - e.mrr_after ELSE 0 END) AS contraction_mrr,
    SUM(CASE WHEN e.event_date >= b.ws AND e.event_type='churn' THEN e.mrr_before - e.mrr_after ELSE 0 END) AS churned_mrr,
    COUNT_IF(e.event_date >= b.ws AND e.event_type='churn') AS churned_customers
  FROM saas_demo.silver.mrr_events e CROSS JOIN b GROUP BY ALL
),
j AS (
  SELECT s.month, s.customer_id, s.segment, s.region, s.plan,
    coalesce(ev.opening_book_mrr,0) AS opening_book_mrr,
    coalesce(ev.new_mrr,0) AS new_mrr, coalesce(ev.expansion_mrr,0) AS expansion_mrr,
    coalesce(ev.contraction_mrr,0) AS contraction_mrr, coalesce(ev.churned_mrr,0) AS churned_mrr,
    coalesce(ev.churned_customers,0) AS churned_customers
  FROM spine s LEFT JOIN ev ON ev.customer_id = s.customer_id AND ev.month = s.month
),
w AS (
  SELECT *, SUM(opening_book_mrr + new_mrr + expansion_mrr - contraction_mrr - churned_mrr)
            OVER (PARTITION BY customer_id ORDER BY month) AS closing_mrr
  FROM j
)
SELECT month, customer_id, segment, region, plan,
  CAST(closing_mrr - (new_mrr + expansion_mrr - contraction_mrr - churned_mrr) AS DECIMAL(14,2)) AS opening_mrr,
  CAST(new_mrr AS DECIMAL(14,2)) AS new_mrr, CAST(expansion_mrr AS DECIMAL(14,2)) AS expansion_mrr,
  CAST(contraction_mrr AS DECIMAL(14,2)) AS contraction_mrr, CAST(churned_mrr AS DECIMAL(14,2)) AS churned_mrr,
  CAST(closing_mrr AS DECIMAL(14,2)) AS closing_mrr,
  CAST(IF(closing_mrr - (new_mrr + expansion_mrr - contraction_mrr - churned_mrr) > 0, 1, 0) AS INT) AS opening_customers,
  CAST(churned_customers AS INT) AS churned_customers
FROM w;

CREATE OR REPLACE MATERIALIZED VIEW `saas_demo`.`gold`.`customer_snapshot` (
  customer_id STRING COLLATE UTF8_BINARY COMMENT 'Unique customer key. Joins to mrr_monthly and the silver tables.',
  company_name STRING COLLATE UTF8_BINARY COMMENT 'Fictional company name, display only.',
  segment STRING COLLATE UTF8_BINARY COMMENT 'Customer size segment (SMB, Mid-Market, Enterprise).',
  region STRING COLLATE UTF8_BINARY COMMENT 'Sales region (NA, EMEA, APAC, LATAM).',
  plan STRING COLLATE UTF8_BINARY COMMENT 'Plan tier (Starter, Pro, Enterprise).',
  signup_date DATE COMMENT 'Date the customer first subscribed. Can be before the 24-month window (opening book).',
  current_mrr DECIMAL(14,2) COMMENT 'MRR at the snapshot date in USD per month. 0 for churned customers.',
  tenure_months INT COMMENT 'Whole months from signup to the snapshot date (active) or to cancellation (churned).',
  status STRING COLLATE UTF8_BINARY COMMENT 'active or churned, as of the snapshot date.',
  churn_month DATE COMMENT 'First day of the month the customer cancelled. NULL means still active.')
COMMENT 'One row per customer as of the end of the last complete month: current MRR (0 if churned), tenure, status and churn month. Joins to mrr_monthly and silver tables on customer_id. Source of saas_customer_metrics.'
AS WITH b AS (SELECT date_sub(trunc(current_date(),'MM'), 1) AS we),
last_row AS (
  SELECT customer_id, closing_mrr FROM saas_demo.gold.mrr_monthly
  QUALIFY row_number() OVER (PARTITION BY customer_id ORDER BY month DESC) = 1
)
SELECT c.customer_id, c.company_name, c.segment, c.region, p.plan_name AS plan, c.signup_date,
  CAST(coalesce(l.closing_mrr, 0) AS DECIMAL(14,2)) AS current_mrr,
  CAST(floor(months_between(coalesce(s.end_date, b.we), c.signup_date)) AS INT) AS tenure_months,
  s.status, trunc(s.end_date, 'MM') AS churn_month
FROM saas_demo.silver.customers c
JOIN saas_demo.silver.subscriptions s USING (customer_id)
JOIN saas_demo.silver.plans p USING (plan_id)
LEFT JOIN last_row l USING (customer_id)
CROSS JOIN b;

CREATE OR REPLACE MATERIALIZED VIEW `saas_demo`.`gold`.`cohort_retention` (
  signup_month DATE COMMENT 'Cohort: the month the customers signed up. Only cohorts inside the 24-month window.',
  months_since_signup INT COMMENT 'Months after signup. 0 = the signup month.',
  customers_start INT COMMENT 'Cohort size. The same on every row of the cohort.',
  customers_active INT COMMENT 'Cohort customers still paying at the end of that month.',
  mrr_start DECIMAL(14,2) COMMENT 'Cohort MRR at the end of its signup month (USD).',
  mrr_now DECIMAL(14,2) COMMENT 'Cohort MRR at the end of that month (USD). Can exceed mrr_start because of expansion.')
COMMENT 'Signup-month cohorts x months since signup. Logo retention = customers_active / customers_start, revenue retention = mrr_now / mrr_start. Do not sum rows within a cohort.'
AS WITH b AS (SELECT trunc(date_sub(trunc(current_date(),'MM'), 1),'MM') AS last_month, add_months(trunc(current_date(),'MM'), -24) AS ws),
cohort AS (
  SELECT trunc(signup_date,'MM') AS signup_month, customer_id FROM saas_demo.silver.customers CROSS JOIN b
  WHERE signup_date >= b.ws
),
start AS (
  SELECT c.signup_month, COUNT(*) AS customers_start, SUM(m.closing_mrr) AS mrr_start
  FROM cohort c JOIN saas_demo.gold.mrr_monthly m ON m.customer_id = c.customer_id AND m.month = c.signup_month
  GROUP BY ALL
),
grid AS (
  SELECT s.*, k AS months_since_signup
  FROM start s CROSS JOIN b
  LATERAL VIEW explode(sequence(0, CAST(months_between(b.last_month, s.signup_month) AS INT))) e AS k
),
act AS (
  SELECT c.signup_month, CAST(months_between(m.month, c.signup_month) AS INT) AS months_since_signup,
    COUNT_IF(m.closing_mrr > 0) AS customers_active, SUM(m.closing_mrr) AS mrr_now
  FROM cohort c JOIN saas_demo.gold.mrr_monthly m USING (customer_id)
  GROUP BY ALL
)
SELECT g.signup_month, g.months_since_signup,
  CAST(g.customers_start AS INT) AS customers_start, CAST(coalesce(a.customers_active,0) AS INT) AS customers_active,
  CAST(g.mrr_start AS DECIMAL(14,2)) AS mrr_start, CAST(coalesce(a.mrr_now,0) AS DECIMAL(14,2)) AS mrr_now
FROM grid g LEFT JOIN act a USING (signup_month, months_since_signup);
