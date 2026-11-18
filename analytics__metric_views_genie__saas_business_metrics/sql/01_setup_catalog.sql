-- Run on a serverless SQL warehouse. Requires CREATE CATALOG on the metastore
-- (or replace saas_demo with an existing catalog where you can CREATE SCHEMA).
CREATE CATALOG IF NOT EXISTS saas_demo COMMENT 'Synthetic SaaS subscription metrics demo (no real data)';
CREATE SCHEMA IF NOT EXISTS saas_demo.silver COMMENT 'Synthetic cleansed entities';
CREATE SCHEMA IF NOT EXISTS saas_demo.gold COMMENT 'Aggregated MVs and metric views';
