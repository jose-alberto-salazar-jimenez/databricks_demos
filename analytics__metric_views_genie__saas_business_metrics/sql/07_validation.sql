-- 1) Row counts (expected: customers 800, plans 5, subscriptions 800, mrr_events ~2,000,
--    mrr_monthly ~10,109, customer_snapshot 800, cohort_retention 300)
SELECT 'silver.customers' t, count(*) n FROM saas_demo.silver.customers UNION ALL
SELECT 'silver.plans', count(*) FROM saas_demo.silver.plans UNION ALL
SELECT 'silver.subscriptions', count(*) FROM saas_demo.silver.subscriptions UNION ALL
SELECT 'silver.mrr_events', count(*) FROM saas_demo.silver.mrr_events UNION ALL
SELECT 'gold.mrr_monthly', count(*) FROM saas_demo.gold.mrr_monthly UNION ALL
SELECT 'gold.customer_snapshot', count(*) FROM saas_demo.gold.customer_snapshot UNION ALL
SELECT 'gold.cohort_retention', count(*) FROM saas_demo.gold.cohort_retention;

-- 2) Reconciliation: every check must return 0
WITH mm AS (
  SELECT month, SUM(opening_mrr) o, SUM(new_mrr) n, SUM(expansion_mrr) e, SUM(contraction_mrr) c, SUM(churned_mrr) ch, SUM(closing_mrr) cl
  FROM saas_demo.gold.mrr_monthly GROUP BY month
), chk AS (SELECT *, LAG(cl) OVER (ORDER BY month) prev_cl FROM mm)
SELECT 'row_level_breaks' k, count(*) v FROM saas_demo.gold.mrr_monthly
  WHERE closing_mrr <> opening_mrr + new_mrr + expansion_mrr - contraction_mrr - churned_mrr
UNION ALL SELECT 'month_level_breaks', count_if(cl <> o+n+e-c-ch) FROM chk
UNION ALL SELECT 'opening_ne_prev_closing', count_if(prev_cl IS NOT NULL AND o <> prev_cl) FROM chk
UNION ALL SELECT 'final_closing_vs_events', (SELECT cl FROM chk ORDER BY month DESC LIMIT 1) - (SELECT SUM(mrr_after - mrr_before) FROM saas_demo.silver.mrr_events)
UNION ALL SELECT 'snapshot_vs_last_month', (SELECT SUM(current_mrr) FROM saas_demo.gold.customer_snapshot) - (SELECT cl FROM chk ORDER BY month DESC LIMIT 1);

-- 3) Semiadditive check: MRR without month must equal the last month, not the sum of months
SELECT MEASURE(`mrr`) AS mrr_latest FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL;
SELECT SUM(closing_mrr) AS last_month_mrr FROM saas_demo.gold.mrr_monthly WHERE month = (SELECT max(month) FROM saas_demo.gold.mrr_monthly);

-- 4) Realism (trailing 12 months): logo churn ~2%/month, annualized NRR ~100-110%
WITH m AS (SELECT * FROM saas_demo.gold.mrr_monthly WHERE month >= add_months(trunc(current_date(),'MM'), -12))
SELECT segment,
  SUM(churned_customers)/SUM(opening_customers) AS monthly_logo_churn,
  pow((SUM(opening_mrr)+SUM(expansion_mrr)-SUM(contraction_mrr)-SUM(churned_mrr))/SUM(opening_mrr), 12) AS annualized_nrr
FROM m GROUP BY ROLLUP(segment) ORDER BY segment;
