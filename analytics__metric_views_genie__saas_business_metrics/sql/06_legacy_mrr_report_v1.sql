-- Deliberately misleading legacy table for the demo: 'churn' is logo churn only.
-- Shows how certification/deprecation steers users (and Genie) to the certified metric view.
CREATE OR REPLACE TABLE saas_demo.silver.mrr_report_v1 AS
SELECT month, segment,
  CAST(SUM(opening_mrr) AS DECIMAL(16,2)) AS opening_mrr,
  CAST(SUM(closing_mrr) AS DECIMAL(16,2)) AS closing_mrr,
  CAST(SUM(opening_customers) AS INT) AS opening_customers,
  CAST(SUM(churned_customers) AS INT) AS churned_customers,
  CAST(SUM(churned_customers) / NULLIF(SUM(opening_customers), 0) AS DOUBLE) AS churn
FROM saas_demo.gold.mrr_monthly
GROUP BY month, segment;
