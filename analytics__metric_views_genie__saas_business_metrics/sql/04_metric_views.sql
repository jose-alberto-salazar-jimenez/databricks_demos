-- Metric views (semantic layer), YAML v1.1. Run each statement separately (some SQL clients split on ';' even inside $$ YAML).
-- revenue_monthly_metrics on customer_mrr_monthly, customer_health_metrics on customer_status_snapshot, revenue_daily_metrics on customer_mrr_daily.
-- Prefer ALTER VIEW ... AS $$ yaml $$ for later edits: CREATE OR REPLACE drops grants and tags.

CREATE OR REPLACE VIEW saas_demo.gold.revenue_monthly_metrics WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: saas_demo.gold.customer_mrr_monthly
comment: SaaS revenue KPIs (USD) on the customer x month MRR waterfall. MRR and ARR are point-in-time (semiadditive over month). Flow measures are summed. Rates over multiple months are pooled monthly rates.
dimensions:
- name: month
  expr: month
  comment: First day of the calendar month the MRR movements and closing balance belong to.
  display_name: Month
  format:
    type: date
    date_format: locale_short_month
  synonyms:
  - period
  - calendar month
- name: segment
  expr: segment
  comment: Customer size segment (SMB, Mid-Market, Enterprise).
  display_name: Customer Segment
  synonyms:
  - customer segment
  - customer size
- name: region
  expr: region
  comment: Sales region of the customer (NA, EMEA, APAC, LATAM).
  display_name: Region
  synonyms:
  - sales region
  - geography
  - geo
- name: plan
  expr: plan
  comment: Subscription plan tier (Starter, Pro, Enterprise).
  display_name: Plan
  synonyms:
  - plan tier
  - subscription plan
  - product tier
measures:
- name: mrr
  expr: SUM(closing_mrr)
  window:
  - order: month
    semiadditive: last
    range: current
  comment: 'Monthly recurring revenue at month end. Point-in-time (semiadditive): summed across customers and segments but never across months. When month is not grouped it returns the last month in scope.'
  display_name: MRR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - recurring revenue
  - monthly recurring revenue
  - MRR balance
- name: arr
  expr: MEASURE(mrr) * 12
  comment: Annual recurring revenue = point-in-time MRR x 12. Inherits the semiadditive behaviour of MRR.
  display_name: ARR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - annual recurring revenue
  - annual run rate
  - run rate
- name: new_mrr
  expr: SUM(new_mrr)
  comment: MRR added by newly signed customers in the period (flow, additive over months).
  display_name: New MRR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - new business MRR
  - new logo MRR
  - new customer MRR
- name: expansion_mrr
  expr: SUM(expansion_mrr)
  comment: MRR increase from existing customers (upsell or seats) in the period.
  display_name: Expansion MRR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - upsell MRR
  - expansion revenue
  - upgrade MRR
- name: contraction_mrr
  expr: SUM(contraction_mrr)
  comment: MRR decrease from customers that downgraded but stayed (positive number).
  display_name: Contraction MRR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - downgrade MRR
  - contraction revenue
- name: churned_mrr
  expr: SUM(churned_mrr)
  comment: MRR lost from customers that cancelled in the period (positive number).
  display_name: Churned MRR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - lost MRR
  - churned revenue
  - cancelled MRR
- name: net_new_mrr
  expr: MEASURE(new_mrr) + MEASURE(expansion_mrr) - MEASURE(contraction_mrr) - MEASURE(churned_mrr)
  comment: New + expansion - contraction - churned MRR. For a single month this equals closing minus opening MRR.
  display_name: Net New MRR
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - net MRR growth
  - net new recurring revenue
  - MRR change
- name: opening_mrr_flow
  expr: SUM(opening_mrr)
  comment: Helper measure. Sum of opening MRR over the months in scope, used as denominator for revenue churn and NRR. Not a point-in-time balance when several months are aggregated.
  display_name: Opening MRR (rate denominator)
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
- name: logo_churn_rate
  expr: SUM(churned_customers) / NULLIF(SUM(opening_customers), 0)
  comment: Churned customers / customers at start of month. Over multiple months this is the pooled average monthly rate.
  display_name: Logo Churn Rate
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - logo churn
  - customer churn
  - customer attrition
- name: gross_revenue_churn_rate
  expr: (MEASURE(churned_mrr) + MEASURE(contraction_mrr)) / NULLIF(MEASURE(opening_mrr_flow), 0)
  comment: (Churned + contraction MRR) / opening MRR. Monthly rate, pooled across months when month is not grouped.
  display_name: Gross Revenue Churn Rate
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue churn
  - MRR churn
  - gross revenue churn
- name: net_revenue_retention
  expr: (MEASURE(opening_mrr_flow) + MEASURE(expansion_mrr) - MEASURE(contraction_mrr) - MEASURE(churned_mrr)) / NULLIF(MEASURE(opening_mrr_flow), 0)
  comment: (Opening + expansion - contraction - churned) / opening MRR, excluding new MRR. Monthly rate, pooled across months when month is not grouped.
  display_name: Net Revenue Retention (monthly)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - NRR
  - net dollar retention
  - NDR
- name: mrr_prev_month
  expr: SUM(closing_mrr)
  window:
  - order: month
    semiadditive: last
    range: current
    offset: -1 month
  comment: MRR at the end of the previous calendar month. Point-in-time like MRR. Without month in the query it refers to the month before the last month in scope.
  display_name: MRR Previous Month
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - last month MRR
  - prior month MRR
- name: mrr_mom_growth
  expr: (MEASURE(mrr) - MEASURE(mrr_prev_month)) / NULLIF(MEASURE(mrr_prev_month), 0)
  comment: Month-over-month MRR growth = (MRR - previous month MRR) / previous month MRR.
  display_name: MRR Growth MoM
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - month over month growth
  - MoM growth
- name: mrr_prior_year
  expr: SUM(closing_mrr)
  window:
  - order: month
    semiadditive: last
    range: current
    offset: -1 year
  comment: MRR at the end of the same calendar month one year earlier. Point-in-time like MRR.
  display_name: MRR Same Month Last Year
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - last year MRR
  - prior year MRR
- name: mrr_yoy_growth
  expr: (MEASURE(mrr) - MEASURE(mrr_prior_year)) / NULLIF(MEASURE(mrr_prior_year), 0)
  comment: Year-over-year MRR growth = (MRR - MRR same month last year) / MRR same month last year. Same rate applies to ARR.
  display_name: MRR Growth YoY
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - year over year growth
  - YoY growth
  - annual growth
  - ARR growth
- name: net_new_mrr_t12m
  expr: MEASURE(net_new_mrr)
  window:
  - order: month
    semiadditive: last
    range: trailing 12 month inclusive
  comment: Net new MRR summed over the 12 months ending with the month in the row (current month included). Without month it uses the last month in scope.
  display_name: Net New MRR (Trailing 12 Months)
  format:
    type: currency
    currency_code: USD
    abbreviation: compact
  synonyms:
  - TTM net new MRR
  - last 12 months net new MRR
- name: logo_churn_rate_t12m
  expr: MEASURE(logo_churn_rate)
  window:
  - order: month
    semiadditive: last
    range: trailing 12 month inclusive
  comment: Average monthly logo churn over the 12 months ending with the month in the row (pooled - churned customers / opening customers across the 12 months).
  display_name: Logo Churn Rate (Trailing 12 Months)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - TTM logo churn
  - average monthly customer churn
- name: gross_revenue_churn_rate_t12m
  expr: MEASURE(gross_revenue_churn_rate)
  window:
  - order: month
    semiadditive: last
    range: trailing 12 month inclusive
  comment: Average monthly gross revenue churn over the 12 months ending with the month in the row (pooled).
  display_name: Gross Revenue Churn Rate (Trailing 12 Months)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - TTM revenue churn
  - average monthly revenue churn
- name: net_revenue_retention_t12m
  expr: MEASURE(net_revenue_retention)
  window:
  - order: month
    semiadditive: last
    range: trailing 12 month inclusive
  comment: Average monthly NRR over the 12 months ending with the month in the row (pooled). Excludes new MRR.
  display_name: Net Revenue Retention (Trailing 12 Months, monthly)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - TTM NRR
- name: net_revenue_retention_annualized
  expr: POWER(MEASURE(net_revenue_retention_t12m), 12)
  comment: Trailing 12-month average monthly NRR compounded over 12 months. An approximation of annual NRR, not a cohort-based 12-month NRR.
  display_name: Net Revenue Retention (Annualized)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - annual NRR
  - yearly net revenue retention
  - annual net dollar retention
$$
;

CREATE OR REPLACE VIEW saas_demo.gold.customer_health_metrics WITH METRICS LANGUAGE YAML AS $$
version: 1.1
source: saas_demo.gold.customer_status_snapshot
comment: Customer base KPIs as of the end of the last complete month (USD).
dimensions:
- name: segment
  expr: segment
  comment: Customer size segment (SMB, Mid-Market, Enterprise).
  display_name: Customer Segment
  synonyms:
  - customer segment
  - customer size
- name: region
  expr: region
  comment: Sales region of the customer (NA, EMEA, APAC, LATAM).
  display_name: Region
  synonyms:
  - sales region
  - geography
  - geo
- name: plan
  expr: plan
  comment: Subscription plan tier (Starter, Pro, Enterprise).
  display_name: Plan
  synonyms:
  - plan tier
  - subscription plan
  - product tier
- name: status
  expr: status
  comment: active = subscription still running at snapshot date, churned = cancelled.
  display_name: Customer Status
  synonyms:
  - customer status
  - account status
  - churn status
measures:
- name: active_customers
  expr: COUNT(1) FILTER (WHERE status = 'active')
  comment: Number of customers with an active subscription at the snapshot date.
  display_name: Active Customers
  synonyms:
  - active accounts
  - paying customers
  - logos
  - customer count
- name: avg_tenure_months
  expr: AVG(tenure_months)
  comment: Average full months from signup to snapshot date (active) or to churn date (churned), over customers in scope. Filter on status to restrict.
  display_name: Avg Tenure (months)
  format:
    type: number
    decimal_places:
      type: exact
      places: 1
  synonyms:
  - average tenure
  - customer lifetime
  - average customer age
- name: arpa
  expr: SUM(current_mrr) FILTER (WHERE status = 'active') / NULLIF(MEASURE(active_customers), 0)
  comment: Average revenue per account = current MRR of active customers / active customers (USD per month).
  display_name: ARPA
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 0
  synonyms:
  - average revenue per account
  - average revenue per customer
  - revenue per account
$$
;

CREATE OR REPLACE VIEW saas_demo.gold.revenue_daily_metrics WITH METRICS LANGUAGE YAML AS $$
version: '1.1'
source: saas_demo.gold.customer_mrr_daily
comment: 'Certified day-level revenue KPIs including the current month to date: daily trends of recognized revenue and MRR movements, recognized revenue over the last 28 / 91 days vs the prior window and month to date vs the same days of the previous month, and MRR vs earlier dates. Without a date in the query, point-in-time and window measures are anchored on the latest date in scope (yesterday).'
dimensions:
- name: date
  expr: date
  comment: Calendar day, from the 24-month window start through yesterday (the current month to date is included).
  display_name: Date
  synonyms:
  - day
  - as of date
- name: month
  expr: DATE_TRUNC('MONTH', date)
  comment: First day of the calendar month of the date. Use it for monthly trends of daily data.
  display_name: Month
  synonyms:
  - calendar month
- name: segment
  expr: segment
  comment: 'Customer size segment: SMB, Mid-Market, Enterprise.'
  display_name: Segment
  synonyms:
  - customer segment
  - customer size
- name: region
  expr: region
  comment: 'Sales region: NA, EMEA, APAC, LATAM.'
  display_name: Region
  synonyms:
  - sales region
  - geography
  - geo
- name: plan
  expr: plan
  comment: 'Plan tier: Starter, Pro, Enterprise.'
  display_name: Plan
  synonyms:
  - plan tier
  - subscription plan
measures:
- name: recognized_revenue
  expr: SUM(recognized_revenue)
  comment: 'Subscription revenue earned in the period: each day earns MRR / days in that month. Adds up over days, so it is the revenue of any date range.'
  display_name: Recognized Revenue
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue
  - subscription revenue
  - earned revenue
- name: net_new_mrr
  expr: SUM(new_mrr + expansion_mrr - contraction_mrr - churned_mrr)
  comment: New + expansion - contraction - churned MRR in the period (USD). Change of the MRR balance.
  display_name: Net New MRR
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - net MRR growth
  - MRR change
- name: new_mrr
  expr: SUM(new_mrr)
  comment: MRR from new customers in the period (USD).
  display_name: New MRR
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - new business MRR
- name: expansion_mrr
  expr: SUM(expansion_mrr)
  comment: MRR increases from existing customers in the period (USD).
  display_name: Expansion MRR
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - upsell MRR
- name: contraction_mrr
  expr: SUM(contraction_mrr)
  comment: MRR decreases from customers who stayed, in the period (USD, positive).
  display_name: Contraction MRR
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - downgrade MRR
- name: churned_mrr
  expr: SUM(churned_mrr)
  comment: MRR lost from cancellations in the period (USD, positive).
  display_name: Churned MRR
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - lost MRR
  - cancelled MRR
- name: new_customers
  expr: SUM(new_customers)
  comment: Customers whose first subscription started in the period.
  display_name: New Customers
  format:
    type: number
    decimal_places:
      type: exact
      places: 0
  synonyms:
  - new logos
  - signups
- name: churned_customers
  expr: SUM(churned_customers)
  comment: Customers who cancelled in the period.
  display_name: Churned Customers
  format:
    type: number
    decimal_places:
      type: exact
      places: 0
  synonyms:
  - lost customers
  - cancellations
- name: mrr
  expr: SUM(closing_mrr)
  window:
  - order: date
    range: current
    semiadditive: last
  comment: 'MRR balance at the end of the day (USD). Point-in-time: without a date in the query it returns the latest date in scope (yesterday).'
  display_name: MRR
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - recurring revenue
  - monthly recurring revenue
  - MRR balance
- name: active_customers
  expr: SUM(is_active)
  window:
  - order: date
    range: current
    semiadditive: last
  comment: Paying customers at the end of the day. Point-in-time.
  display_name: Active Customers
  format:
    type: number
    decimal_places:
      type: exact
      places: 0
  synonyms:
  - active accounts
  - paying customers
- name: recognized_revenue_l28d
  expr: SUM(recognized_revenue)
  window:
  - order: date
    range: trailing 28 day inclusive
    semiadditive: last
  comment: Recognized revenue over the 28 days ending on the latest date in scope (inclusive).
  display_name: Recognized Revenue (last 28 days)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue last 28 days
- name: recognized_revenue_p28d
  expr: SUM(recognized_revenue)
  window:
  - order: date
    range: trailing 28 day inclusive
    semiadditive: last
    offset: -28 day
  comment: Recognized revenue over the 28 days before the last-28-days window.
  display_name: Recognized Revenue (prior 28 days)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue prior 28 days
- name: recognized_revenue_l91d
  expr: SUM(recognized_revenue)
  window:
  - order: date
    range: trailing 91 day inclusive
    semiadditive: last
  comment: Recognized revenue over the 91 days ending on the latest date in scope (inclusive).
  display_name: Recognized Revenue (last 91 days)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue last 91 days
- name: recognized_revenue_p91d
  expr: SUM(recognized_revenue)
  window:
  - order: date
    range: trailing 91 day inclusive
    semiadditive: last
    offset: -91 day
  comment: Recognized revenue over the 91 days before the last-91-days window.
  display_name: Recognized Revenue (prior 91 days)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue prior 91 days
- name: recognized_revenue_mtd
  expr: SUM(recognized_revenue)
  window:
  - order: date
    range: cumulative
    semiadditive: last
  - order: month
    range: current
    semiadditive: last
  comment: Recognized revenue over the 1st of the month through the latest date in scope.
  display_name: Recognized Revenue (month to date)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue month to date
- name: recognized_revenue_pmtd
  expr: SUM(recognized_revenue)
  window:
  - order: date
    range: cumulative
    semiadditive: last
    offset: -1 month
  - order: month
    range: current
    semiadditive: last
    offset: -1 month
  comment: Recognized revenue over the same days of the previous month (day 1 to the same day number, capped at that month end).
  display_name: Recognized Revenue (previous month to date)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
  synonyms:
  - revenue previous month to date
- name: recognized_revenue_l28d_change
  expr: (MEASURE(recognized_revenue_l28d) - MEASURE(recognized_revenue_p28d)) / NULLIF(MEASURE(recognized_revenue_p28d), 0)
  comment: Recognized revenue growth, last 28 days vs prior 28 days.
  display_name: Recognized Revenue Change (last 28 days vs prior 28 days)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 1
  synonyms:
  - revenue growth last 28 days vs prior 28 days
- name: recognized_revenue_l91d_change
  expr: (MEASURE(recognized_revenue_l91d) - MEASURE(recognized_revenue_p91d)) / NULLIF(MEASURE(recognized_revenue_p91d), 0)
  comment: Recognized revenue growth, last 91 days vs prior 91 days.
  display_name: Recognized Revenue Change (last 91 days vs prior 91 days)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 1
  synonyms:
  - revenue growth last 91 days vs prior 91 days
- name: recognized_revenue_mtd_change
  expr: (MEASURE(recognized_revenue_mtd) - MEASURE(recognized_revenue_pmtd)) / NULLIF(MEASURE(recognized_revenue_pmtd), 0)
  comment: Recognized revenue growth, month to date vs the same days of the previous month.
  display_name: Recognized Revenue Change (month to date vs the same days of the previous month)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 1
  synonyms:
  - revenue growth month to date vs the same days of the previous month
- name: mrr_28d_ago
  expr: SUM(closing_mrr)
  window:
  - order: date
    range: current
    semiadditive: last
    offset: -28 day
  comment: MRR balance on 28 days earlier (USD). Point-in-time.
  display_name: MRR (28 days earlier)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
- name: mrr_change_28d
  expr: (MEASURE(mrr) - MEASURE(mrr_28d_ago)) / NULLIF(MEASURE(mrr_28d_ago), 0)
  comment: MRR growth vs 28 days earlier.
  display_name: MRR Change (vs 28 days earlier)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 1
- name: mrr_91d_ago
  expr: SUM(closing_mrr)
  window:
  - order: date
    range: current
    semiadditive: last
    offset: -91 day
  comment: MRR balance on 91 days earlier (USD). Point-in-time.
  display_name: MRR (91 days earlier)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
- name: mrr_change_91d
  expr: (MEASURE(mrr) - MEASURE(mrr_91d_ago)) / NULLIF(MEASURE(mrr_91d_ago), 0)
  comment: MRR growth vs 91 days earlier.
  display_name: MRR Change (vs 91 days earlier)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 1
- name: mrr_prev_month_same_day
  expr: SUM(closing_mrr)
  window:
  - order: date
    range: current
    semiadditive: last
    offset: -1 month
  comment: MRR balance on the same day of the previous month (capped at month end) (USD). Point-in-time.
  display_name: MRR (the same day of the previous month)
  format:
    type: currency
    currency_code: USD
    decimal_places:
      type: exact
      places: 2
- name: mrr_change_mom_same_day
  expr: (MEASURE(mrr) - MEASURE(mrr_prev_month_same_day)) / NULLIF(MEASURE(mrr_prev_month_same_day), 0)
  comment: MRR growth vs the same day of the previous month (capped at month end).
  display_name: MRR Change (vs the same day of the previous month)
  format:
    type: percentage
    decimal_places:
      type: exact
      places: 1
$$
;
