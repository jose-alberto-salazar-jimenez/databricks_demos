# Question bank (validated SQL, metric views + MEASURE())

Values were checked on 2026-11-17 (last complete month = Oct 2026). Rates are monthly;
over several months they are pooled monthly averages. Ambiguous questions have two valid answers
and are intentionally NOT used as Genie benchmarks (a benchmark has one ground truth, so it would
penalize Genie for correctly asking "logo or revenue churn?").

## Audience A - Finance / RevOps (`gold.saas_revenue_metrics`)

| # | Question | SQL |
| --- | --- | --- |
| A1 | What is our current MRR? | ``SELECT MEASURE(`mrr`) AS mrr FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL`` |
| A2 | What is current ARR by segment? | ``SELECT `segment`, MEASURE(`arr`) AS arr FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL ORDER BY arr DESC`` |
| A3 | How has MRR trended over the last 12 months? | ``SELECT `month`, MEASURE(`mrr`) AS mrr FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL ORDER BY `month` `` |
| A4 | What is the monthly MRR waterfall? | ``SELECT `month`, MEASURE(`new_mrr`), MEASURE(`expansion_mrr`), MEASURE(`contraction_mrr`), MEASURE(`churned_mrr`), MEASURE(`net_new_mrr`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL ORDER BY `month` `` |
| A5 | What is NRR by segment (last 12 months)? | ``SELECT `segment`, MEASURE(`net_revenue_retention`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL`` |
| A6 | Logo and revenue churn by segment (last 12 months)? | ``SELECT `segment`, MEASURE(`logo_churn_rate`), MEASURE(`gross_revenue_churn_rate`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL`` |
| A7 | Which region added the most net new MRR in the last 3 months? | ``SELECT `region`, MEASURE(`net_new_mrr`) AS n FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -3) GROUP BY ALL ORDER BY n DESC`` |
| A8 (ambiguous) | What is our churn? (1) logo, (2) revenue | ``SELECT MEASURE(`logo_churn_rate`), MEASURE(`gross_revenue_churn_rate`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` = add_months(trunc(current_date(),'MM'), -1) GROUP BY ALL`` |
| A9 (ambiguous) | What is our revenue? (1) ARR run-rate, (2) trailing-12-month recurring revenue | (1) ``SELECT MEASURE(`arr`) FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL`` (2) ``WITH m AS (SELECT `month`, MEASURE(`mrr`) AS mrr FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL) SELECT SUM(mrr) FROM m`` |
| A10 (ambiguous) | How much did we grow? (1) net new MRR, (2) YoY MRR % | (1) ``SELECT MEASURE(`net_new_mrr`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL`` (2) ``WITH m AS (SELECT `month`, MEASURE(`mrr`) AS mrr FROM saas_demo.gold.saas_revenue_metrics WHERE `month` IN (add_months(trunc(current_date(),'MM'), -1), add_months(trunc(current_date(),'MM'), -13)) GROUP BY ALL) SELECT max_by(mrr, `month`) / min_by(mrr, `month`) - 1 FROM m`` |

## Audience B - Customer success (`gold.saas_customer_metrics`, `gold.cohort_retention`)

| # | Question | SQL |
| --- | --- | --- |
| B1 | How many active customers do we have? | ``SELECT MEASURE(`active_customers`) FROM saas_demo.gold.saas_customer_metrics GROUP BY ALL`` |
| B2 | Active customers and ARPA by segment? | ``SELECT `segment`, MEASURE(`active_customers`), MEASURE(`arpa`) FROM saas_demo.gold.saas_customer_metrics GROUP BY ALL`` |
| B3 | ARPA by plan and region? | ``SELECT `plan`, `region`, MEASURE(`arpa`) FROM saas_demo.gold.saas_customer_metrics GROUP BY ALL`` |
| B4 | Tenure of churned customers by segment? | ``SELECT `segment`, MEASURE(`avg_tenure_months`) FROM saas_demo.gold.saas_customer_metrics WHERE `status` = 'churned' GROUP BY ALL`` |
| B5 | Region with the lowest Enterprise ARPA? | ``SELECT `region`, MEASURE(`arpa`) AS arpa FROM saas_demo.gold.saas_customer_metrics WHERE `segment` = 'Enterprise' GROUP BY ALL ORDER BY arpa LIMIT 1`` |
| B6 | 6-month retention per cohort (table, no metric view) | `SELECT signup_month, customers_active / customers_start, mrr_now / mrr_start FROM saas_demo.gold.cohort_retention WHERE months_since_signup = 6 ORDER BY signup_month` |
| B7 | Tenure active vs churned by segment? | ``SELECT `segment`, `status`, MEASURE(`avg_tenure_months`) FROM saas_demo.gold.saas_customer_metrics GROUP BY ALL`` |
| B8 (ambiguous) | What is our retention? (1) 12-month logo retention, (2) NRR | (1) `SELECT SUM(customers_active)/SUM(customers_start) FROM saas_demo.gold.cohort_retention WHERE months_since_signup = 12` (2) ``SELECT MEASURE(`net_revenue_retention`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL`` |
| B9 (ambiguous) | Average tenure? (1) all customers, (2) active only | ``SELECT MEASURE(`avg_tenure_months`) FROM saas_demo.gold.saas_customer_metrics [WHERE `status` = 'active'] GROUP BY ALL`` |
| B10 (ambiguous) | Which segments are shrinking? (1) total MRR down, (2) NRR < 100% | (1) 3-month MRR change per segment, (2) ``SELECT `segment`, MEASURE(`net_revenue_retention`) AS nrr FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -3) GROUP BY ALL HAVING nrr < 1`` |

Demo insight for B10: no segment loses total MRR (SMB only +$4.5K in 3 months), but SMB existing customers shrink (NRR 98.4%/month) - new SMB logos mask it.

## Time-comparison measures (added after P1)

| Question | SQL |
| --- | --- |
| How is MRR growing MoM and YoY? | ``SELECT `month`, MEASURE(`mrr`), MEASURE(`mrr_mom_growth`), MEASURE(`mrr_yoy_growth`) FROM saas_demo.gold.saas_revenue_metrics WHERE `month` >= add_months(trunc(current_date(),'MM'), -12) GROUP BY ALL ORDER BY `month` `` |
| What is our MRR growth year over year? (= A10 meaning 2, now a single measure) | ``SELECT MEASURE(`mrr_yoy_growth`) FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL`` |
| What is annualized NRR by segment? | ``SELECT `segment`, MEASURE(`net_revenue_retention_annualized`) FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL`` |
| Net new MRR over the last 12 months, by region | ``SELECT `region`, MEASURE(`net_new_mrr_t12m`) FROM saas_demo.gold.saas_revenue_metrics GROUP BY ALL`` |

Values (Oct 2026): MRR growth MoM +2.19%, YoY +76.8%; annualized NRR 105.4% (Ent 118.1%, Mid 102.1%, SMB 81.4%); trailing-12-month logo churn 2.03%/month.

