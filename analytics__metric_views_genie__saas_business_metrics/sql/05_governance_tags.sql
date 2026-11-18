-- Prerequisite: account-level governed tags (create once, see scripts/deploy_governance.py or the UI):
--   Revenue, Revenue/RecurringRevenue, Revenue/CustomerHealth (key-only)
--   system.certification_status is a built-in system tag (values certified / deprecated)

-- Domain tags (Discover subdomains). Parent domain 'Revenue' is inherited in browse, not tagged.
ALTER MATERIALIZED VIEW saas_demo.gold.mrr_monthly        SET TAGS ('Revenue/RecurringRevenue');
ALTER VIEW              saas_demo.gold.saas_revenue_metrics SET TAGS ('Revenue/RecurringRevenue');
ALTER MATERIALIZED VIEW saas_demo.gold.customer_snapshot  SET TAGS ('Revenue/CustomerHealth');
ALTER MATERIALIZED VIEW saas_demo.gold.cohort_retention   SET TAGS ('Revenue/CustomerHealth');
ALTER VIEW              saas_demo.gold.saas_customer_metrics SET TAGS ('Revenue/CustomerHealth');

-- Certification
ALTER MATERIALIZED VIEW saas_demo.gold.mrr_monthly          SET TAGS ('system.certification_status' = 'certified');
ALTER MATERIALIZED VIEW saas_demo.gold.customer_snapshot    SET TAGS ('system.certification_status' = 'certified');
ALTER MATERIALIZED VIEW saas_demo.gold.cohort_retention     SET TAGS ('system.certification_status' = 'certified');
ALTER VIEW              saas_demo.gold.saas_revenue_metrics  SET TAGS ('system.certification_status' = 'certified');
ALTER VIEW              saas_demo.gold.saas_customer_metrics SET TAGS ('system.certification_status' = 'certified');
ALTER TABLE             saas_demo.silver.mrr_report_v1       SET TAGS ('system.certification_status' = 'deprecated');
