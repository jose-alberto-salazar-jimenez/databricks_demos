-- Synthetic, reproducible silver layer. Deterministic: every random draw is a hash of
-- (seed 'saas_demo_v1', salt, key), so a rebuild in the same calendar month gives identical data.
-- The 24-month window is computed from current_date(): the 24 complete months before today.
-- About 3/8 of customers are an OPENING BOOK: they signed up in the 36 months before the window.
-- Their 'new' event is dated at the real signup date (before the window) with their MRR at window start,
-- churn / expansion / contraction are simulated only inside the window.
-- Run all statements in ONE session (temporary function and views are session-scoped).

CREATE OR REPLACE TEMPORARY FUNCTION u(salt STRING, k STRING) RETURNS DOUBLE
RETURN (xxhash64(concat_ws('|', 'saas_demo_v1', salt, k)) & 2147483647) / 2147483648.0;

CREATE OR REPLACE TABLE saas_demo.silver.plans
COMMENT 'Synthetic price plans' AS
SELECT * FROM VALUES
 ('PLN-STARTER-M','Starter','monthly'), ('PLN-STARTER-A','Starter','annual'),
 ('PLN-PRO-M','Pro','monthly'), ('PLN-PRO-A','Pro','annual'),
 ('PLN-ENT-A','Enterprise','annual') AS t(plan_id, plan_name, billing_period);

CREATE OR REPLACE TABLE saas_demo.silver.customers
COMMENT 'Synthetic customers (fake names, no personal data). ~3/8 signed up before the 24-month window (opening book), the rest inside it.' AS
WITH b AS (
  SELECT add_months(trunc(current_date(),'MM'), -24) AS ws, date_sub(trunc(current_date(),'MM'), 1) AS we
), ids AS (SELECT id, (id*389) % 1000 AS nidx, format_string('CUST-%05d', id) AS customer_id FROM range(1, 801) AS r(id))
SELECT
  customer_id,
  concat_ws(' ',
    element_at(array('Amber','Birch','Cobalt','Dune','Ember','Fjord','Granite','Harbor','Indigo','Juniper','Kestrel','Lumen','Maple','Nova','Onyx','Pine','Quill','Ridge','Sable','Tundra','Umber','Vela','Willow','Xylo','Yarrow','Zephyr','Aster','Basalt','Cedar','Drift','Ferro','Glacier','Halcyon','Iris','Jade','Krona','Lark','Mosaic','Nimbus','Orchid'),
               cast(nidx % 40 AS INT)+1),
    element_at(array('Analytics','Logistics','Robotics','Metrics','Freight','Studio','Dynamics','Labs','Systems','Networks','Ventures','Software','Supply','Energy','Retail','Bioworks','Data','Works','Fabrication','Cloudworks','Insights','Mobility','Telematics','Payments','Learning'),
               cast(floor(nidx / 40) AS INT)+1),
    element_at(array('Inc.','LLC','Ltd.','GmbH','Group','Co.','S.A.','Pty Ltd'), cast(floor(u('n3', customer_id)*8) AS INT)+1)
  ) AS company_name,
  CASE WHEN u('seg', customer_id) < 0.55 THEN 'SMB' WHEN u('seg', customer_id) < 0.85 THEN 'Mid-Market' ELSE 'Enterprise' END AS segment,
  CASE WHEN u('reg', customer_id) < 0.45 THEN 'NA' WHEN u('reg', customer_id) < 0.75 THEN 'EMEA'
       WHEN u('reg', customer_id) < 0.90 THEN 'APAC' ELSE 'LATAM' END AS region,
  CASE WHEN u('pre', customer_id) < 0.375
       THEN date_sub(b.ws, 1 + cast(floor(u('sig', customer_id) * 1095) AS INT))
       ELSE date_add(b.ws, cast(floor((0.5*u('sig', customer_id) + 0.5*sqrt(u('sig', customer_id))) * (datediff(b.we, b.ws)+1)) AS INT)) END AS signup_date
FROM ids CROSS JOIN b;

-- Customer x month simulation (k = 0 is the signup event, k >= 1 are window months).
-- Tuned so that blended monthly logo churn is ~2% and annualized NRR is 100-110%.
CREATE OR REPLACE TEMPORARY VIEW sim_base AS
WITH b AS (SELECT date_sub(trunc(current_date(),'MM'), 1) AS we, add_months(trunc(current_date(),'MM'), -24) AS ws),
c AS (
  SELECT c.*,
    CASE c.segment
      WHEN 'SMB'        THEN CASE WHEN u('pl', customer_id) < 0.80 THEN 'Starter' ELSE 'Pro' END
      WHEN 'Mid-Market' THEN CASE WHEN u('pl', customer_id) < 0.20 THEN 'Starter' WHEN u('pl', customer_id) < 0.85 THEN 'Pro' ELSE 'Enterprise' END
      ELSE CASE WHEN u('pl', customer_id) < 0.25 THEN 'Pro' ELSE 'Enterprise' END END AS tier,
    CASE c.segment WHEN 'SMB' THEN 0.030 WHEN 'Mid-Market' THEN 0.017 ELSE 0.007 END AS p_churn,
    CASE c.segment WHEN 'SMB' THEN 0.060 WHEN 'Mid-Market' THEN 0.090 ELSE 0.100 END AS p_exp,
    0.03 AS p_con,
    c.signup_date < b.ws AS is_pre, b.ws,
    CASE WHEN c.signup_date < b.ws THEN CAST(months_between(trunc(b.we,'MM'), b.ws) AS INT) + 1
         ELSE CAST(months_between(trunc(b.we,'MM'), trunc(c.signup_date,'MM')) AS INT) END AS max_k
  FROM saas_demo.silver.customers c CROSS JOIN b
),
c2 AS (
  SELECT *,
    CASE tier WHEN 'Starter' THEN 100 + 500*pow(u('m0', customer_id),1.5)
              WHEN 'Pro' THEN 600 + 2400*pow(u('m0', customer_id),1.5)
              ELSE 3000 + 5000*pow(u('m0', customer_id),1.2) END * IF(is_pre, 1.2, 1.0) AS mrr0_raw,
    CASE tier WHEN 'Starter' THEN IF(u('bp', customer_id) < 0.3, 'PLN-STARTER-A', 'PLN-STARTER-M')
              WHEN 'Pro' THEN IF(u('bp', customer_id) < 0.5, 'PLN-PRO-A', 'PLN-PRO-M')
              ELSE 'PLN-ENT-A' END AS plan_id
  FROM c
),
m AS (
  SELECT c2.*, k, IF(is_pre, add_months(ws, k - 1), add_months(trunc(signup_date,'MM'), k)) AS month_start,
    u('ch', concat(customer_id, ':', k)) AS uc, u('ex', concat(customer_id, ':', k)) AS ue,
    u('co', concat(customer_id, ':', k)) AS uk, u('sz', concat(customer_id, ':', k)) AS us,
    u('dy', concat(customer_id, ':', k)) AS ud
  FROM c2 LATERAL VIEW explode(sequence(0, max_k)) e AS k
)
SELECT *,
  CASE WHEN k = 0 THEN 0.0
       WHEN ue < p_exp THEN ln(1.10 + 0.35*us)
       WHEN uk < p_con THEN ln(0.75 + 0.20*us)
       ELSE 0.0 END AS logf,
  (k >= 1 AND uc < p_churn) AS churn_flag
FROM m;

CREATE OR REPLACE TEMPORARY VIEW sim AS
WITH f AS (
  SELECT *, MIN(CASE WHEN churn_flag THEN k END) OVER (PARTITION BY customer_id) AS churn_k
  FROM sim_base
), p AS (
  SELECT *,
    CAST(round(least(12000, greatest(100, mrr0_raw * exp(SUM(logf) OVER (PARTITION BY customer_id ORDER BY k)))) / 10) * 10 AS DECIMAL(12,2)) AS mrr_path
  FROM f WHERE churn_k IS NULL OR k <= churn_k
)
SELECT *,
  LAG(mrr_path) OVER (PARTITION BY customer_id ORDER BY k) AS prev_mrr,
  CASE WHEN k = 0 THEN signup_date
       ELSE date_add(month_start, cast(floor(ud * day(last_day(month_start))) AS INT)) END AS evt_date
FROM p;

CREATE OR REPLACE TABLE saas_demo.silver.subscriptions
COMMENT 'Synthetic subscriptions: one per customer, start = signup, end_date null while active' AS
SELECT format_string('SUB-%05d', cast(substr(customer_id, 6) AS INT)) AS subscription_id,
  customer_id, plan_id, signup_date AS start_date,
  MAX(CASE WHEN k = churn_k THEN evt_date END) AS end_date,
  IF(MAX(churn_k) IS NULL, 'active', 'churned') AS status
FROM sim GROUP BY customer_id, plan_id, signup_date;

CREATE OR REPLACE TABLE saas_demo.silver.mrr_events
COMMENT 'Synthetic MRR movements (USD). event_type: new / expansion / contraction / churn' AS
WITH e AS (
  SELECT customer_id, evt_date AS event_date, 'new' AS event_type, CAST(0 AS DECIMAL(12,2)) AS mrr_before, mrr_path AS mrr_after
  FROM sim WHERE k = 0
  UNION ALL
  SELECT customer_id, evt_date, 'churn', prev_mrr, CAST(0 AS DECIMAL(12,2)) FROM sim WHERE k = churn_k
  UNION ALL
  SELECT customer_id, evt_date, IF(mrr_path > prev_mrr, 'expansion', 'contraction'), prev_mrr, mrr_path
  FROM sim WHERE k >= 1 AND (churn_k IS NULL OR k < churn_k) AND mrr_path <> prev_mrr
)
SELECT format_string('EVT-%06d', row_number() OVER (ORDER BY event_date, customer_id, event_type)) AS event_id, *
FROM e;
