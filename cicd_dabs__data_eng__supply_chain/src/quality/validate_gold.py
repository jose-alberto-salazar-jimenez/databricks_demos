# Databricks notebook source
# MAGIC %md
# MAGIC # Validate gold tables
# MAGIC
# MAGIC Post-pipeline smoke tests run by the job. The task fails (and the job run is marked failed) if any check fails,
# MAGIC which is what the CD workflow uses to stop a bad change before it reaches prod.

# COMMAND ----------

dbutils.widgets.text("catalog", "dev_demo")
dbutils.widgets.text("schema", "supply_chain")
fqn = f"`{dbutils.widgets.get('catalog')}`.`{dbutils.widgets.get('schema')}`"

CHECKS = {
    "gold_sales_performance has rows": f"SELECT COUNT(*) > 0 FROM {fqn}.gold_sales_performance",
    "sales targets joined from Excel": f"SELECT COUNT_IF(target_amount IS NOT NULL) > 0 FROM {fqn}.gold_sales_performance",
    "gold_delivery_performance has rows": f"SELECT COUNT(*) > 0 FROM {fqn}.gold_delivery_performance",
    "on_time_rate within [0, 1]": f"SELECT COUNT_IF(on_time_rate < 0 OR on_time_rate > 1) = 0 FROM {fqn}.gold_delivery_performance",
    "inventory covers all warehouses x SKUs": f"SELECT COUNT(*) = 32 FROM {fqn}.gold_inventory_coverage",
    "gold_machine_oee has rows": f"SELECT COUNT(*) > 0 FROM {fqn}.gold_machine_oee",
    "OEE within [0, 1]": f"SELECT COUNT_IF(oee < 0 OR oee > 1) = 0 FROM {fqn}.gold_machine_oee",
    "late_shipments never exceed delivered": f"SELECT COUNT_IF(late_shipments > delivered) = 0 FROM {fqn}.gold_delivery_performance",
    "avg_freight_cost is positive": f"SELECT COUNT_IF(avg_freight_cost <= 0) = 0 FROM {fqn}.gold_delivery_performance",
}

results = {name: bool(spark.sql(sql).collect()[0][0]) for name, sql in CHECKS.items()}
for name, ok in results.items():
    print(f"{'PASS' if ok else 'FAIL'}  {name}")

failed = [name for name, ok in results.items() if not ok]
if failed:
    raise AssertionError(f"{len(failed)} gold data quality check(s) failed: {failed}")
print(f"All {len(results)} checks passed for {fqn}")
