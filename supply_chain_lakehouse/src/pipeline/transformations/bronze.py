"""Bronze layer: incremental, append-only ingestion of every raw source with Auto Loader.

Each table keeps the source payload as delivered plus lineage columns
(`_source_file`, `_ingested_at`). Explicit schemas make ingestion deterministic
across dev and prod.
"""
from pyspark import pipelines as dp
from pyspark.sql import DataFrame
from pyspark.sql import functions as F

LANDING_PATH = spark.conf.get("landing_path")


def auto_loader(folder: str, fmt: str, schema: str, **options: str) -> DataFrame:
    reader = spark.readStream.format("cloudFiles").option("cloudFiles.format", fmt)
    for key, value in options.items():
        reader = reader.option(key, value)
    return (
        reader.schema(schema)
        .load(f"{LANDING_PATH}/{folder}")
        .withColumn("_source_file", F.col("_metadata.file_path"))
        .withColumn("_ingested_at", F.current_timestamp())
    )


BRONZE_PROPS = {"quality": "bronze"}


# ---------------------------------------------------------------- Salesforce (CRM)
@dp.table(name="bronze_sf_accounts", comment="Salesforce Account extracts (JSON).", table_properties=BRONZE_PROPS)
def bronze_sf_accounts():
    return auto_loader(
        "salesforce/accounts",
        "json",
        "account_id STRING, account_name STRING, industry STRING, region STRING, "
        "annual_revenue DOUBLE, created_date STRING, last_modified STRING",
    )


@dp.table(name="bronze_sf_opportunities", comment="Salesforce Opportunity extracts (JSON).", table_properties=BRONZE_PROPS)
def bronze_sf_opportunities():
    return auto_loader(
        "salesforce/opportunities",
        "json",
        "opportunity_id STRING, account_id STRING, opportunity_name STRING, stage STRING, amount DOUBLE, "
        "probability INT, close_date STRING, owner STRING, last_modified STRING",
    )


# ---------------------------------------------------------------- Excel (Finance)
@dp.table(name="bronze_excel_sales_targets", comment="Finance sales targets workbooks (xlsx).", table_properties=BRONZE_PROPS)
def bronze_excel_sales_targets():
    return auto_loader(
        "excel/sales_targets",
        "excel",
        "region STRING, month STRING, target_amount DOUBLE, owner STRING",
        headerRows="1",
        **{"cloudFiles.schemaEvolutionMode": "none"},
    )


# ---------------------------------------------------------------- ERP
@dp.table(name="bronze_erp_orders", comment="ERP sales order exports (CSV).", table_properties=BRONZE_PROPS)
def bronze_erp_orders():
    return auto_loader(
        "erp/orders",
        "csv",
        "order_id STRING, account_id STRING, sku STRING, quantity INT, unit_price DOUBLE, "
        "order_date STRING, warehouse_id STRING, order_status STRING",
        header="true",
    )


@dp.table(name="bronze_erp_inventory", comment="ERP inventory snapshots (CSV).", table_properties=BRONZE_PROPS)
def bronze_erp_inventory():
    return auto_loader(
        "erp/inventory",
        "csv",
        "snapshot_ts STRING, warehouse_id STRING, sku STRING, on_hand_qty INT, reorder_point INT",
        header="true",
    )


# ---------------------------------------------------------------- Logistics
@dp.table(name="bronze_logistics_shipments", comment="Carrier / TMS shipment events (JSON).", table_properties=BRONZE_PROPS)
def bronze_logistics_shipments():
    return auto_loader(
        "logistics/shipments",
        "json",
        "shipment_id STRING, order_id STRING, carrier STRING, warehouse_id STRING, ship_date STRING, "
        "promised_date STRING, delivered_date STRING, status STRING, freight_cost DOUBLE",
    )


# ---------------------------------------------------------------- Manufacturing IoT
@dp.table(name="bronze_mfg_machine_telemetry", comment="Hourly machine telemetry from plant IoT gateways (JSON).", table_properties=BRONZE_PROPS)
def bronze_mfg_machine_telemetry():
    return auto_loader(
        "manufacturing/telemetry",
        "json",
        "reading_ts STRING, plant_id STRING, machine_id STRING, status STRING, units_produced INT, "
        "units_scrapped INT, ideal_units_per_hour INT, temperature_c DOUBLE, vibration_mm_s DOUBLE",
    )
