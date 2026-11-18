-- Monthly refresh, task 2 of 3: run on a SQL warehouse (sql_task).
-- The gold materialized views were created on a DBSQL warehouse and can only be refreshed from one
-- (serverless generic compute fails with INVALID_PARAMETER_VALUE).
-- Order matters: customer_snapshot and cohort_retention read mrr_monthly.
REFRESH MATERIALIZED VIEW saas_demo.gold.mrr_monthly;
REFRESH MATERIALIZED VIEW saas_demo.gold.customer_snapshot;
REFRESH MATERIALIZED VIEW saas_demo.gold.cohort_retention;

-- Legacy deprecated table (same as sql/06), rebuilt on the refreshed mrr_monthly.
CREATE OR REPLACE TABLE saas_demo.silver.mrr_report_v1 AS
SELECT month, segment,
  CAST(SUM(opening_mrr) AS DECIMAL(16,2)) AS opening_mrr,
  CAST(SUM(closing_mrr) AS DECIMAL(16,2)) AS closing_mrr,
  CAST(SUM(opening_customers) AS INT) AS opening_customers,
  CAST(SUM(churned_customers) AS INT) AS churned_customers,
  CAST(SUM(churned_customers) / NULLIF(SUM(opening_customers), 0) AS DOUBLE) AS churn
FROM saas_demo.gold.mrr_monthly
GROUP BY month, segment;
