# Discover setup - Revenue domain, subdomains and Pages

Exact content of the Discover objects used in this demo (as of 2026-11-20): one domain, two subdomains and 10 Pages.
Discover objects are not deployable from SQL, so create them in the UI (or with the Beta domains API) using
the values below. Domain sections feature the metric views and both Genie Agents.

## Prerequisites

* Governed tags `Revenue`, `Revenue/RecurringRevenue`, `Revenue/CustomerHealth` exist (`scripts/deploy_governance_and_genie.py`).
* Gold objects and Genie Agents carry the subdomain tags (`sql/05_governance_tags.sql`, deploy script) - tagged assets appear in the domain automatically.
* Curator permission: `MANAGE DISCOVER` (account / workspace admins have it by default) or `MANAGE DOMAIN`.

## 1. Domain and subdomains

| Object | Governed tag | Subtitle | Description |
| --- | --- | --- | --- |
| Domain **Revenue** | `Revenue` | Subscription revenue and customer health metrics | Certified recurring-revenue and customer-base metrics for the synthetic SaaS demo: MRR, ARR, churn, net revenue retention, active customers, ARPA and cohort retention. Source: catalog saas_demo, gold schema. |
| Subdomain **RecurringRevenue** | `Revenue/RecurringRevenue` | MRR, ARR, revenue churn and NRR | Monthly recurring revenue waterfall and revenue KPIs. Primary asset: saas_demo.gold.saas_revenue_metrics. |
| Subdomain **CustomerHealth** | `Revenue/CustomerHealth` | Customer base, tenure, logo churn and cohort retention | Active customers, ARPA, tenure and signup-cohort retention. Primary asset: saas_demo.gold.saas_customer_metrics. |

UI steps:
1. Discover > **Create domain** > select the existing governed tag `Revenue` > fill Subtitle and Description > **Create** (stays draft).
2. Open **Revenue** > **Create subdomain** > **Use an existing tag** > `Revenue/RecurringRevenue` > fill fields > **Create**. Repeat for `Revenue/CustomerHealth`.
3. **Edit Sections** to feature the metric views and both Genie Agents (RecurringRevenue: `saas_revenue_metrics` + Genie Agent "Revenue and Retention"; CustomerHealth: `saas_customer_metrics` + Genie Agent "Customer Success"). **Publish** after review.

Note: creating a domain through the API published it immediately (`isDraft: false`); set it back to draft if you want a review step.

## 2. Pages (10, owner = demo author)

The Page duplicate checker flags several of these terms as overlapping because they share words (revenue, MRR, customer,
logo, churn). They are distinct business terms; accept the flags when creating them.

To publish a draft: Discover > **Pages** > **Show drafts** > open the Page > **Publish** (Page managers and curators only).

Each Page has a one-sentence description, synonyms, a body with the definition, and linked assets.

### MRR - subdomain RecurringRevenue
* **Description:** Month-end recurring subscription revenue, the core point-in-time revenue balance.
* **Synonyms:** recurring revenue
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** ARR, Revenue churn, Net revenue retention, MRR growth YoY

```markdown
## Definition
Monthly value of all active subscriptions at month end, in USD. A point-in-time snapshot; never sum it across months.

## Business use
Query the `mrr` measure in `saas_demo.gold.saas_revenue_metrics`. It is semiadditive: it adds up across segments, regions and plans, but when month is not grouped it returns the last month in scope instead of a sum.
```

### ARR - subdomain RecurringRevenue
* **Description:** Annualized run-rate of recurring revenue derived from closing MRR.
* **Synonyms:** annual recurring revenue
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** MRR, MRR growth YoY

```markdown
## Definition
Closing MRR x 12.

## Business use
Query the `arr` measure in `saas_demo.gold.saas_revenue_metrics`. Like MRR it is point-in-time and is never summed across months.
```

### Revenue churn - subdomain RecurringRevenue
* **Description:** Share of opening recurring revenue lost to cancellations and downgrades in a month.
* **Synonyms:** gross revenue churn, MRR churn
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** MRR, Net revenue retention

```markdown
## Definition
(Churned MRR + contraction MRR) / opening MRR.

## Business use
Query the `gross_revenue_churn_rate` measure in `saas_demo.gold.saas_revenue_metrics`. It is a monthly rate; across several months it is the pooled average monthly rate. Not the same as logo churn, which counts customers rather than revenue.
```

### Net revenue retention - subdomain RecurringRevenue
* **Description:** How much recurring revenue the existing customer base keeps month over month, including upsell.
* **Synonyms:** NRR, net dollar retention
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** MRR, Revenue churn, Annualized NRR

```markdown
## Definition
(Opening MRR + expansion - contraction - churned) / opening MRR. Excludes new customers.

## Business use
Query the `net_revenue_retention` measure in `saas_demo.gold.saas_revenue_metrics`. It is a monthly rate; above 100% means the existing base grows even without new customers.
```

### MRR growth YoY - subdomain RecurringRevenue
* **Description:** Year-over-year growth of month-end recurring revenue.
* **Synonyms:** year over year growth, YoY growth, annual MRR growth, ARR growth
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** MRR, ARR

```markdown
## Definition
(MRR this month - MRR in the same month last year) / MRR in the same month last year. The same rate applies to ARR.

## Business use
Query the `mrr_yoy_growth` measure in `saas_demo.gold.saas_revenue_metrics`; `mrr_mom_growth` gives month-over-month growth.
```

### Annualized NRR - subdomain RecurringRevenue
* **Description:** Trailing 12-month net revenue retention expressed as an annual rate.
* **Synonyms:** annual NRR, annualized net revenue retention, annual net dollar retention
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** Net revenue retention

```markdown
## Definition
The average monthly NRR over the trailing 12 months (pooled), compounded over 12 months: POWER(NRR trailing 12 months, 12). An approximation of annual NRR, not a cohort-based 12-month NRR.

## Business use
Query the `net_revenue_retention_annualized` measure in `saas_demo.gold.saas_revenue_metrics`.
```

### Logo churn - subdomain CustomerHealth
* **Description:** Share of customers at the start of a month who cancelled during that month.
* **Synonyms:** customer churn, customer attrition
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`, `saas_demo.gold.saas_customer_metrics` (both listed under Related assets in the UI)
* **Related Pages:** Active customer, Cohort retention (related-Page links only work within the same subdomain, so it cannot link to Revenue churn)

```markdown
## Definition
Customers who cancelled in the month / customers at the start of the month.

## Business use
Query the `logo_churn_rate` measure in `saas_demo.gold.saas_revenue_metrics`. It is a monthly rate; across several months it is the pooled average monthly rate. It counts customers, not revenue - for lost revenue see Revenue churn. For current customer-base context (active customers, tenure, ARPA) use `saas_demo.gold.saas_customer_metrics`.
```

### ARPA - subdomain CustomerHealth
* **Description:** Average monthly recurring revenue per active customer account.
* **Synonyms:** average revenue per account, average revenue per customer, revenue per account
* **Linked assets:** `saas_demo.gold.saas_customer_metrics`
* **Related Pages:** Active customer

```markdown
## Definition
Current MRR of active customers / number of active customers, in USD per month, as of the end of the last complete month.

## Business use
Query the `arpa` measure in `saas_demo.gold.saas_customer_metrics` with `MEASURE()`.
```

### Active customer - subdomain CustomerHealth
* **Description:** A customer account with an active, paying subscription at the snapshot date.
* **Synonyms:** paying customer, active account, logo, customer count
* **Linked assets:** `saas_demo.gold.saas_customer_metrics`
* **Related Pages:** ARPA, Logo churn

```markdown
## Definition
A customer whose subscription is active (status = active, MRR above 0) at the end of the last complete month; churned customers are excluded.

## Business use
Count with the `active_customers` measure in `saas_demo.gold.saas_customer_metrics`.
```

### Cohort retention - subdomain CustomerHealth
* **Description:** How much of a signup-month cohort's customers and revenue remain N months after signup.
* **Synonyms:** cohort logo retention, cohort revenue retention, retention curve
* **Linked assets:** `saas_demo.gold.cohort_retention`
* **Related Pages:** Logo churn

```markdown
## Definition
For a signup-month cohort, logo retention = customers still active / customers at signup; revenue retention = cohort MRR now / cohort MRR at the end of the signup month. Never sum rows within a cohort.

## Business use
Query `saas_demo.gold.cohort_retention` filtered on `months_since_signup` (e.g. 6 or 12).
```

## Setup checklist

- [ ] Domain and both subdomains created with the subtitles and descriptions above
- [ ] 10 Pages created (check Related assets in the UI; an API read-back may list only one linked asset per Page)
- [ ] Domain sections feature both metric views and both Genie Agents
- [ ] Publish domain, subdomains, then Pages
