# Discover setup - Revenue domain, subdomains and Pages

Exact content of the Discover objects used in this demo, read back from the live workspace on 2026-11-18.
Discover objects are not deployable from SQL, so recreate them in the UI (or with the Beta domains API) using
the values below. The domain, both subdomains and all 5 Pages were reviewed and **published on 2026-11-18**;
domain sections feature the metric views and both Genie Agents.

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
3. **Edit Sections** to feature the metric views and both Genie Agents (RecurringRevenue: `saas_revenue_metrics` + Genie Agent "Revenue and Retention"; CustomerHealth: `saas_customer_metrics` + Genie Agent "Customer Success"). **Publish** after review (done for this demo on 2026-11-18).

Note: creating a domain through the API published it immediately (`isDraft: false`); set it back to draft if you want a review step.

## 2. Pages (published, owner = demo author)

To publish a draft: Discover > **Pages** > **Show drafts** > open the Page > **Publish** (Page managers and curators only).

Each Page has a one-sentence description, synonyms, a body with the definition, and linked assets.

### MRR - subdomain RecurringRevenue
* **Description:** Month-end recurring subscription revenue, the core point-in-time revenue balance.
* **Synonyms:** recurring revenue
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`
* **Related Pages:** ARR, Revenue churn, Net revenue retention

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
* **Related Pages:** MRR

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
* **Related Pages:** MRR, Revenue churn

```markdown
## Definition
(Opening MRR + expansion - contraction - churned) / opening MRR. Excludes new customers.

## Business use
Query the `net_revenue_retention` measure in `saas_demo.gold.saas_revenue_metrics`. It is a monthly rate; above 100% means the existing base grows even without new customers.
```

### Logo churn - subdomain CustomerHealth
* **Description:** Share of customers at the start of a month who cancelled during that month.
* **Synonyms:** customer churn, customer attrition
* **Linked assets:** `saas_demo.gold.saas_revenue_metrics`, `saas_demo.gold.saas_customer_metrics` (both listed under Related assets in the UI)
* **Related Pages:** none (related-Page links only work within the same subdomain, so it cannot link to Revenue churn)

```markdown
## Definition
Customers who cancelled in the month / customers at the start of the month.

## Business use
Query the `logo_churn_rate` measure in `saas_demo.gold.saas_revenue_metrics`. It is a monthly rate; across several months it is the pooled average monthly rate. It counts customers, not revenue - for lost revenue see Revenue churn. For current customer-base context (active customers, tenure, ARPA) use `saas_demo.gold.saas_customer_metrics`.
```

## 3. Suggested next Pages (not yet created)

ARPA, Active customer, Cohort retention (CustomerHealth); MRR growth MoM / YoY and Annualized NRR (RecurringRevenue) - matching the time-comparison measures in `saas_revenue_metrics`.

## Checklist before publishing (completed 2026-11-18)

- [x] Domain and both subdomains: subtitle and description reviewed
- [x] 5 Pages reviewed (check Related assets in the UI; an API read-back may list only one linked asset per Page)
- [x] Domain sections feature both metric views and both Genie Agents
- [x] Publish domain, subdomains, then Pages
