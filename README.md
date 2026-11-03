# Databricks Demos

Customer enablement demos for Databricks.

This repo collects practical examples that help customers learn and adopt Databricks, including:

- **Jobs** — scheduled and triggered workloads
- **Pipelines** — Lakeflow / Delta Live Tables and related data pipelines
- **DABs** — Databricks Asset Bundles for packaging and deploying assets

Use these demos as starting points for workshops, POCs, and enablement sessions.

## Demos

| Demo | What it shows |
| --- | --- |
| [cicd_dabs__data_eng__supply_chain](cicd_dabs__data_eng__supply_chain/README.md) | CI/CD with Declarative Automation Bundles + GitHub Actions: simulated Salesforce, Excel, ERP, logistics and IoT sources -> Lakeflow Spark Declarative Pipeline (bronze/silver/gold) -> Lakeflow Job, promoted dev -> prod |
| [api_autoloader__data_eng__open_meteo_weather](api_autoloader__data_eng__open_meteo_weather/README.md) | Incremental daily REST API ingestion (Open-Meteo weather for a lat/lon grid, default Costa Rica +/-10 deg): land raw JSON in a UC volume -> Auto Loader bronze -> silver MERGE, as a parameterized serverless Lakeflow Job |
