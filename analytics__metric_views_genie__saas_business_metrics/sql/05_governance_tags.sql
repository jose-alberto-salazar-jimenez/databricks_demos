-- Prerequisite: account-level governed tags (create once, see scripts/deploy_governance.py or the UI):
--   Revenue, Revenue/RecurringRevenue, Revenue/CustomerHealth (key-only)
--   system.certification_status is a built-in system tag (values certified / deprecated)

-- Domain tags (Discover subdomains). Parent domain 'Revenue' is inherited in browse, not tagged.
ALTER MATERIALIZED VIEW saas_demo.gold.customer_mrr_daily          SET TAGS ('Revenue/RecurringRevenue');
ALTER MATERIALIZED VIEW saas_demo.gold.customer_mrr_monthly        SET TAGS ('Revenue/RecurringRevenue');
ALTER VIEW              saas_demo.gold.revenue_daily_metrics        SET TAGS ('Revenue/RecurringRevenue');
ALTER VIEW              saas_demo.gold.revenue_monthly_metrics SET TAGS ('Revenue/RecurringRevenue');
ALTER MATERIALIZED VIEW saas_demo.gold.customer_status_snapshot  SET TAGS ('Revenue/CustomerHealth');
ALTER MATERIALIZED VIEW saas_demo.gold.signup_cohort_retention_monthly   SET TAGS ('Revenue/CustomerHealth');
ALTER VIEW              saas_demo.gold.customer_health_metrics SET TAGS ('Revenue/CustomerHealth');

-- Certification
ALTER MATERIALIZED VIEW saas_demo.gold.customer_mrr_daily            SET TAGS ('system.certification_status' = 'certified');
ALTER MATERIALIZED VIEW saas_demo.gold.customer_mrr_monthly          SET TAGS ('system.certification_status' = 'certified');
ALTER VIEW              saas_demo.gold.revenue_daily_metrics          SET TAGS ('system.certification_status' = 'certified');
ALTER MATERIALIZED VIEW saas_demo.gold.customer_status_snapshot    SET TAGS ('system.certification_status' = 'certified');
ALTER MATERIALIZED VIEW saas_demo.gold.signup_cohort_retention_monthly     SET TAGS ('system.certification_status' = 'certified');
ALTER VIEW              saas_demo.gold.revenue_monthly_metrics  SET TAGS ('system.certification_status' = 'certified');
ALTER VIEW              saas_demo.gold.customer_health_metrics SET TAGS ('system.certification_status' = 'certified');
ALTER TABLE             saas_demo.silver.mrr_report_v1       SET TAGS ('system.certification_status' = 'deprecated');
