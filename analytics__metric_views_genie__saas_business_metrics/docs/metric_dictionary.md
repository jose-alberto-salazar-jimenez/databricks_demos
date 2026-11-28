# Metric dictionary

Every metric, dimension and column in the `saas_demo` catalog, in one place. Definitions are taken from the
metric view YAML (`sql/04_metric_views.sql`), the gold SQL (`sql/03_gold_materialized_views.sql`) and the column
comments (`sql/08_column_comments.sql`); the same text is visible in Catalog Explorer. Business definitions for the
10 key terms are also published as Discover Pages (`docs/discover_setup.md`). All amounts are USD.

Use the **metric views** for answers (query measures with `MEASURE()`); the materialized views and silver tables are
listed for lineage and detail queries.

Official documentation (Databricks on AWS): [Unity Catalog metric views](https://docs.databricks.com/aws/en/uc-semantics/metric-views/index/),
[Metric view YAML syntax reference](https://docs.databricks.com/aws/en/uc-semantics/metric-views/yaml-reference/) (measures, formats, synonyms),
[Advanced techniques for metric views](https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques/) (window and semiadditive measures).
The full reference list is at the end of the [README](../README.md#references-official-databricks-on-aws-documentation).

## Conventions

| Term | Meaning |
| --- | --- |
| Point-in-time (semiadditive) | A balance at a moment (MRR, ARR, active customers). Adds up across customers, segments, regions and plans, never across months or days. When the time dimension is not grouped, the measure returns the last month or day in scope |
| Flow | A movement during a period (new, expansion, contraction, churned MRR, recognized revenue, customer counts). Adds up over any period |
| Monthly rate, pooled | A rate per month (churn, NRR). Over several months it is the pooled average monthly rate: sum of numerators / sum of denominators, not the average of monthly rates |
| Trailing 12 months (T12M) | The row month plus the 11 months before it (`trailing 12 month inclusive`) |
| Window anchor | Window measures without a date or month in the query are anchored on the latest month (monthly view) or latest date (daily view) in scope |
| Data window | Monthly objects: the 24 complete months before the current month. Daily objects: the same window plus the current month through yesterday |
| Opening MRR | MRR at the start of the month = previous month closing MRR. Opening-book customers (signed up before the window) start the window with their existing MRR, which is not counted as new MRR |

## Which object answers which question

| Question type | Object |
| --- | --- |
| MRR, ARR, MRR waterfall, revenue churn, logo churn, NRR, MoM / YoY growth, trailing 12 months, by month | `gold.revenue_monthly_metrics` |
| Customer counts over time: active customers per month, new / churned / net new customers, ARPA by month, segments shrinking by logos | `gold.revenue_monthly_metrics` |
| Daily trends, recognized revenue, last 28 / 91 days, month to date, MRR vs N days ago | `gold.revenue_daily_metrics` |
| Current customer base: active customers, ARPA, tenure, churned vs active | `gold.customer_health_metrics` |
| Signup-cohort retention curves | `gold.signup_cohort_retention_monthly` (no metric view yet) |
| Account lists (which customers churned, company names) | `gold.customer_status_snapshot` |
| Never use | `silver.mrr_report_v1` (deprecated: its `churn` is logo churn only) |

## Metric view: `gold.revenue_monthly_metrics`

Source: `gold.customer_mrr_monthly` (customer x complete month). Tags: `Revenue/RecurringRevenue`, certified.

### Dimensions

| Name | Display name | Definition | Synonyms |
| --- | --- | --- | --- |
| `month` | Month | First day of the calendar month the MRR movements and closing balance belong to | period, calendar month |
| `segment` | Customer Segment | Customer size segment (SMB, Mid-Market, Enterprise) | customer segment, customer size |
| `region` | Region | Sales region of the customer (NA, EMEA, APAC, LATAM) | sales region, geography, geo |
| `plan` | Plan | Subscription plan tier (Starter, Pro, Enterprise) | plan tier, subscription plan, product tier |

### Measures

| Name | Display name | Definition | Type | Format | Synonyms |
| --- | --- | --- | --- | --- | --- |
| `mrr` | MRR | Monthly recurring revenue at month end: `SUM(closing_mrr)` | Point-in-time (window: month, current, semiadditive last) | USD, compact | recurring revenue, monthly recurring revenue, MRR balance |
| `arr` | ARR | Annual recurring revenue = MRR x 12 | Point-in-time | USD, compact | annual recurring revenue, annual run rate, run rate |
| `new_mrr` | New MRR | MRR added by newly signed customers in the period | Flow | USD, compact | new business MRR, new logo MRR, new customer MRR |
| `expansion_mrr` | Expansion MRR | MRR increase from existing customers (upsell or seats) | Flow | USD, compact | upsell MRR, expansion revenue, upgrade MRR |
| `contraction_mrr` | Contraction MRR | MRR decrease from customers that downgraded but stayed (positive number) | Flow | USD, compact | downgrade MRR, contraction revenue |
| `churned_mrr` | Churned MRR | MRR lost from customers that cancelled (positive number) | Flow | USD, compact | lost MRR, churned revenue, cancelled MRR |
| `net_new_mrr` | Net New MRR | New + expansion - contraction - churned MRR. For a single month = closing - opening MRR | Flow | USD, compact | net MRR growth, net new recurring revenue, MRR change |
| `opening_mrr_flow` | Opening MRR (rate denominator) | Helper: sum of opening MRR over the months in scope, the denominator of revenue churn and NRR. Not a balance when several months are aggregated. Hidden in the Genie Agents | Helper | USD, compact | - |
| `logo_churn_rate` | Logo Churn Rate | Churned customers / customers at the start of the month | Monthly rate, pooled | %, 2 decimals | logo churn, customer churn, customer attrition |
| `gross_revenue_churn_rate` | Gross Revenue Churn Rate | (Churned + contraction MRR) / opening MRR | Monthly rate, pooled | %, 2 decimals | revenue churn, MRR churn, gross revenue churn |
| `net_revenue_retention` | Net Revenue Retention (monthly) | (Opening + expansion - contraction - churned MRR) / opening MRR. Excludes new MRR | Monthly rate, pooled | %, 2 decimals | NRR, net dollar retention, NDR |
| `mrr_prev_month` | MRR Previous Month | MRR at the end of the previous calendar month | Point-in-time (window offset -1 month) | USD, compact | last month MRR, prior month MRR |
| `mrr_mom_growth` | MRR Growth MoM | (MRR - previous month MRR) / previous month MRR | Rate | %, 2 decimals | month over month growth, MoM growth |
| `mrr_prior_year` | MRR Same Month Last Year | MRR at the end of the same month one year earlier | Point-in-time (window offset -1 year) | USD, compact | last year MRR, prior year MRR |
| `mrr_yoy_growth` | MRR Growth YoY | (MRR - MRR same month last year) / MRR same month last year. The same rate applies to ARR | Rate | %, 2 decimals | year over year growth, YoY growth, annual growth, ARR growth |
| `net_new_mrr_t12m` | Net New MRR (Trailing 12 Months) | Net new MRR summed over the 12 months ending with the row month | Flow over T12M window | USD, compact | TTM net new MRR, last 12 months net new MRR |
| `logo_churn_rate_t12m` | Logo Churn Rate (Trailing 12 Months) | Average monthly logo churn over T12M (pooled) | Monthly rate, pooled over T12M | %, 2 decimals | TTM logo churn, average monthly customer churn |
| `gross_revenue_churn_rate_t12m` | Gross Revenue Churn Rate (Trailing 12 Months) | Average monthly gross revenue churn over T12M (pooled) | Monthly rate, pooled over T12M | %, 2 decimals | TTM revenue churn, average monthly revenue churn |
| `net_revenue_retention_t12m` | Net Revenue Retention (Trailing 12 Months, monthly) | Average monthly NRR over T12M (pooled). Excludes new MRR | Monthly rate, pooled over T12M | %, 2 decimals | TTM NRR |
| `net_revenue_retention_annualized` | Net Revenue Retention (Annualized) | `POWER(net_revenue_retention_t12m, 12)`: T12M monthly NRR compounded over 12 months. An approximation, not a cohort-based 12-month NRR | Annual rate | %, 2 decimals | annual NRR, yearly net revenue retention, annual net dollar retention |
| `active_customers` | Active Customers (month end) | Paying customers at month end: `COUNT_IF(closing_mrr > 0)` | Point-in-time (window: month, current, semiadditive last) | - | active accounts, paying customers, logos, customer count |
| `new_customers` | New Customers | Customers who signed up in the period (inside the window; opening-book customers are not counted): `COUNT_IF(new_mrr > 0)` | Flow | - | new logos, signups, new accounts |
| `churned_customers` | Churned Customers | Customers who cancelled in the period | Flow | - | lost customers, cancellations, churned logos |
| `net_new_customers` | Net New Customers | New - churned customers. For a single month = active customers at month end - the month before; negative = shrinking by logos | Flow | - | net new logos, logo growth, net customer change |
| `arpa` | ARPA (month end) | Month-end MRR / active customers at month end (USD per month) | Point-in-time ratio | USD, 0 decimals | average revenue per account, average revenue per customer, revenue per account |

Customer counts reconcile: for every month and segment, active customers = previous month active + new - churned (0 breaks). For the last complete month, `active_customers` and `arpa` equal the same measures in `customer_health_metrics` (587 customers; Enterprise ARPA $6,098). Use `customer_health_metrics` for the current base by status and tenure, and `revenue_monthly_metrics` for counts over time.

Bare "churn" and "attrition" are deliberately not synonyms of either churn rate: they are ambiguous, and the Genie Agents show both rates.

## Metric view: `gold.revenue_daily_metrics`

Source: `gold.customer_mrr_daily` (customer x day, through yesterday). Tags: `Revenue/RecurringRevenue`, certified.
Without a date in the query, point-in-time and window measures are anchored on the latest date in scope (yesterday).

### Dimensions

| Name | Display name | Definition | Synonyms |
| --- | --- | --- | --- |
| `date` | Date | Calendar day, from the 24-month window start through yesterday (current month to date included) | day, as of date |
| `month` | Month | First day of the calendar month of the date (`DATE_TRUNC('MONTH', date)`), for monthly trends of daily data | calendar month |
| `segment` | Segment | Customer size segment: SMB, Mid-Market, Enterprise | customer segment, customer size |
| `region` | Region | Sales region: NA, EMEA, APAC, LATAM | sales region, geography, geo |
| `plan` | Plan | Plan tier: Starter, Pro, Enterprise | plan tier, subscription plan |

### Measures

| Name | Display name | Definition | Type | Format | Synonyms |
| --- | --- | --- | --- | --- | --- |
| `recognized_revenue` | Recognized Revenue | Subscription revenue earned: each day earns MRR / days in that month | Flow | USD, 2 decimals | revenue, subscription revenue, earned revenue |
| `net_new_mrr` | Net New MRR | New + expansion - contraction - churned MRR in the period | Flow | USD, 2 decimals | net MRR growth, MRR change |
| `new_mrr` | New MRR | MRR from new customers | Flow | USD, 2 decimals | new business MRR |
| `expansion_mrr` | Expansion MRR | MRR increases from existing customers | Flow | USD, 2 decimals | upsell MRR |
| `contraction_mrr` | Contraction MRR | MRR decreases from customers who stayed (positive) | Flow | USD, 2 decimals | downgrade MRR |
| `churned_mrr` | Churned MRR | MRR lost from cancellations (positive) | Flow | USD, 2 decimals | lost MRR, cancelled MRR |
| `new_customers` | New Customers | Customers whose first subscription started in the period | Flow | Number | new logos, signups |
| `churned_customers` | Churned Customers | Customers who cancelled in the period | Flow | Number | lost customers, cancellations |
| `mrr` | MRR | MRR balance at the end of the day | Point-in-time (window: date, current, semiadditive last) | USD, 2 decimals | recurring revenue, monthly recurring revenue, MRR balance |
| `active_customers` | Active Customers | Paying customers at the end of the day | Point-in-time | Number | active accounts, paying customers |
| `recognized_revenue_l28d` | Recognized Revenue (last 28 days) | Recognized revenue over the 28 days ending on the latest date in scope (inclusive) | Flow over window | USD, 2 decimals | revenue last 28 days |
| `recognized_revenue_p28d` | Recognized Revenue (prior 28 days) | Recognized revenue over the 28 days before the last-28-days window (offset -28 days, no overlap) | Flow over window | USD, 2 decimals | revenue prior 28 days |
| `recognized_revenue_l91d` | Recognized Revenue (last 91 days) | Recognized revenue over the 91 days ending on the latest date in scope (inclusive) | Flow over window | USD, 2 decimals | revenue last 91 days |
| `recognized_revenue_p91d` | Recognized Revenue (prior 91 days) | Recognized revenue over the 91 days before the last-91-days window | Flow over window | USD, 2 decimals | revenue prior 91 days |
| `recognized_revenue_mtd` | Recognized Revenue (month to date) | Recognized revenue from the 1st of the month through the latest date in scope | Flow over window | USD, 2 decimals | revenue month to date |
| `recognized_revenue_pmtd` | Recognized Revenue (previous month to date) | Recognized revenue over the same days of the previous month (day 1 to the same day number, capped at that month's end) | Flow over window | USD, 2 decimals | revenue previous month to date |
| `recognized_revenue_l28d_change` | Recognized Revenue Change (last 28 days vs prior 28 days) | (l28d - p28d) / p28d | Rate | %, 1 decimal | revenue growth last 28 days vs prior 28 days |
| `recognized_revenue_l91d_change` | Recognized Revenue Change (last 91 days vs prior 91 days) | (l91d - p91d) / p91d | Rate | %, 1 decimal | revenue growth last 91 days vs prior 91 days |
| `recognized_revenue_mtd_change` | Recognized Revenue Change (month to date vs the same days of the previous month) | (mtd - pmtd) / pmtd | Rate | %, 1 decimal | revenue growth month to date vs the same days of the previous month |
| `mrr_28d_ago` | MRR (28 days earlier) | MRR balance 28 days earlier | Point-in-time (offset -28 days) | USD, 2 decimals | - |
| `mrr_change_28d` | MRR Change (vs 28 days earlier) | (MRR - MRR 28 days earlier) / MRR 28 days earlier | Rate | %, 1 decimal | - |
| `mrr_91d_ago` | MRR (91 days earlier) | MRR balance 91 days earlier | Point-in-time (offset -91 days) | USD, 2 decimals | - |
| `mrr_change_91d` | MRR Change (vs 91 days earlier) | (MRR - MRR 91 days earlier) / MRR 91 days earlier | Rate | %, 1 decimal | - |
| `mrr_prev_month_same_day` | MRR (the same day of the previous month) | MRR balance on the same day of the previous month (capped at month end) | Point-in-time (offset -1 month) | USD, 2 decimals | - |
| `mrr_change_mom_same_day` | MRR Change (vs the same day of the previous month) | (MRR - MRR same day previous month) / MRR same day previous month | Rate | %, 1 decimal | - |

Each comparison period is its own measure: a metric view measure cannot take the period as a parameter.

## Metric view: `gold.customer_health_metrics`

Source: `gold.customer_status_snapshot` (one row per customer as of the end of the last complete month). Tags: `Revenue/CustomerHealth`, certified.

### Dimensions

| Name | Display name | Definition | Synonyms |
| --- | --- | --- | --- |
| `segment` | Customer Segment | Customer size segment (SMB, Mid-Market, Enterprise) | customer segment, customer size |
| `region` | Region | Sales region of the customer (NA, EMEA, APAC, LATAM) | sales region, geography, geo |
| `plan` | Plan | Subscription plan tier (Starter, Pro, Enterprise) | plan tier, subscription plan, product tier |
| `status` | Customer Status | active = subscription still running at the snapshot date, churned = cancelled | customer status, account status, churn status |

### Measures

| Name | Display name | Definition | Type | Format | Synonyms |
| --- | --- | --- | --- | --- | --- |
| `active_customers` | Active Customers | Number of customers with an active subscription at the snapshot date: `COUNT(1) FILTER (WHERE status = 'active')` | Point-in-time count | - | active accounts, paying customers, logos, customer count |
| `avg_tenure_months` | Avg Tenure (months) | Average full months from signup to the snapshot date (active) or to the churn date (churned), over customers in scope. Filter on `status` to restrict | Average | Number, 1 decimal | average tenure, customer lifetime, average customer age |
| `arpa` | ARPA | Average revenue per account = current MRR of active customers / active customers (USD per month) | Ratio | USD, 0 decimals | average revenue per account, average revenue per customer, revenue per account |

Cross-check: ARPA x active customers = MRR of the last complete month (e.g. Enterprise $6,098 x 105 = $640,270 on 2026-11-27).

## Gold materialized views

### `gold.customer_mrr_daily` (core fact)

One row per customer per day the subscription was live, from the window start (or signup) through cancellation or yesterday.

| Column | Definition |
| --- | --- |
| `date` | Calendar day. With `customer_id`, the unique key |
| `customer_id` | Customer key. Joins to the silver tables and the other gold tables |
| `segment`, `region`, `plan` | From `customers` and `plans` |
| `closing_mrr` | MRR balance at the end of the day (running total of MRR events). 0 on the cancellation day. Point-in-time: never sum across days |
| `is_active` | 1 if the customer had MRR at the end of the day. Sum = active customers that day |
| `new_mrr` | MRR from a first subscription that day (signups inside the window only) |
| `expansion_mrr` | MRR increase that day |
| `contraction_mrr` | MRR decrease that day while the customer stays (positive) |
| `churned_mrr` | MRR lost on the cancellation day (positive) |
| `new_customers` | 1 on the signup day (inside the window) |
| `churned_customers` | 1 on the cancellation day |
| `recognized_revenue` | `closing_mrr` / days in the month. Adds up over any date range |

### `gold.customer_mrr_monthly`

Customer x complete month, rolled up from `customer_mrr_daily`. Source of `revenue_monthly_metrics`.

| Column | Definition |
| --- | --- |
| `month` | First day of the calendar month. With `customer_id`, the unique key |
| `customer_id`, `segment`, `region`, `plan` | Customer key and attributes |
| `opening_mrr` | MRR at the start of the month (= previous closing) = closing - (new + expansion - contraction - churned) |
| `new_mrr` | MRR from a first subscription signed inside the window; only in the signup month |
| `expansion_mrr` | MRR increases during the month |
| `contraction_mrr` | MRR decreases while the customer stays (positive) |
| `churned_mrr` | MRR lost in the churn month (positive) |
| `closing_mrr` | MRR at month end. 0 in the churn month. Never sum across months |
| `opening_customers` | 1 if the customer had MRR at the start of the month. Sum = customers at month start (logo churn denominator) |
| `churned_customers` | 1 if the customer cancelled in the month |

### `gold.customer_status_snapshot`

One row per customer as of the end of the last complete month (current-month signups not included). Source of `customer_health_metrics`.

| Column | Definition |
| --- | --- |
| `customer_id` | Unique customer key |
| `company_name` | Fictional company name, display only |
| `segment`, `region`, `plan` | Customer attributes |
| `signup_date` | Date of first subscription; can be before the window (opening book) |
| `current_mrr` | MRR at the snapshot date. 0 for churned customers |
| `tenure_months` | Whole months from signup to the snapshot date (active) or to cancellation (churned) |
| `status` | active or churned at the snapshot date |
| `churn_month` | First day of the month the customer cancelled. NULL = active |

### `gold.signup_cohort_retention_monthly`

Signup-month cohort x months since signup (cohorts inside the window, complete months only). Do not sum rows within a cohort.

| Column | Definition |
| --- | --- |
| `signup_month` | Cohort: the month the customers signed up |
| `months_since_signup` | Months after signup; 0 = the signup month |
| `customers_start` | Cohort size (same on every row of the cohort) |
| `customers_active` | Cohort customers still paying at the end of that month |
| `mrr_start` | Cohort MRR at the end of its signup month |
| `mrr_now` | Cohort MRR at the end of that month; can exceed `mrr_start` because of expansion |

Derived metrics: logo retention = `customers_active / customers_start`; revenue retention = `mrr_now / mrr_start`. Across cohorts, pool with `SUM(customers_active) / SUM(customers_start)`.

## Silver tables

| Table | Column | Definition |
| --- | --- | --- |
| `customers` | `customer_id` | Unique customer key (CUST-nnnnn); main join key |
| | `company_name` | Fictional company name, display only |
| | `segment` | SMB, Mid-Market or Enterprise; fixed for the customer lifetime |
| | `region` | NA, EMEA, APAC or LATAM |
| | `signup_date` | Date of first subscription (= `subscriptions.start_date`); can be before the window |
| `plans` | `plan_id` | Unique plan key, e.g. PLN-PRO-M |
| | `plan_name` | Starter, Pro or Enterprise |
| | `billing_period` | monthly or annual invoicing; MRR is always stated per month |
| `subscriptions` | `subscription_id` | Unique subscription key (SUB-nnnnn); one per customer |
| | `customer_id`, `plan_id` | Owner and plan; the plan does not change |
| | `start_date` | Signup date |
| | `end_date` | Cancellation date; NULL = active |
| | `status` | active or churned (churned exactly when `end_date` is set) |
| `mrr_events` | `event_id` | Unique event key, numbered in date order |
| | `customer_id` | Customer whose MRR changed |
| | `event_date` | Date the change took effect |
| | `event_type` | new = first MRR, expansion = increase, contraction = decrease while staying, churn = cancellation (MRR to 0) |
| | `mrr_before`, `mrr_after` | MRR just before / after the event. Sum of (after - before) per customer = current MRR |

### Deprecated: `silver.mrr_report_v1`

Legacy monthly report by segment, kept for the demo. Tagged `system.certification_status = deprecated`.

| Column | Definition |
| --- | --- |
| `month`, `segment` | Month and customer segment |
| `opening_mrr`, `closing_mrr` | Total MRR at the start / end of the month |
| `opening_customers`, `churned_customers` | Customers paying at month start / cancelled during the month |
| `churn` | **Logo churn only** (churned / opening customers). Says nothing about lost revenue. Use `logo_churn_rate`, `gross_revenue_churn_rate` and `net_revenue_retention` in `revenue_monthly_metrics` instead |
