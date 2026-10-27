"""Silver layer: typed, de-duplicated, conformed entities with data quality expectations."""
from pyspark import pipelines as dp
from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

SILVER_PROPS = {"quality": "silver"}


def latest_per_key(df: DataFrame, keys: list[str], order_col: str) -> DataFrame:
    """Keep the most recent version of each business key (sources re-send records)."""
    w = Window.partitionBy(*keys).orderBy(F.col(order_col).desc(), F.col("_ingested_at").desc())
    return df.withColumn("_rn", F.row_number().over(w)).filter("_rn = 1").drop("_rn")


# ---------------------------------------------------------------- Sales
@dp.materialized_view(name="silver_accounts", comment="Current Salesforce accounts.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("valid_account_id", "account_id IS NOT NULL")
@dp.expect("known_region", "region IN ('NORTH_AMERICA', 'LATAM', 'EMEA', 'APAC')")
def silver_accounts():
    df = spark.read.table("bronze_sf_accounts").withColumn("last_modified", F.to_timestamp("last_modified"))
    return latest_per_key(df, ["account_id"], "last_modified").select(
        "account_id",
        "account_name",
        "industry",
        "region",
        "annual_revenue",
        F.to_date("created_date").alias("created_date"),
        "last_modified",
    )


@dp.materialized_view(name="silver_opportunities", comment="Current Salesforce opportunities.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("valid_opportunity_id", "opportunity_id IS NOT NULL")
@dp.expect_or_drop("non_negative_amount", "amount >= 0")
@dp.expect("valid_probability", "probability BETWEEN 0 AND 100")
def silver_opportunities():
    df = spark.read.table("bronze_sf_opportunities").withColumn("last_modified", F.to_timestamp("last_modified"))
    return latest_per_key(df, ["opportunity_id"], "last_modified").select(
        "opportunity_id",
        "account_id",
        "opportunity_name",
        "stage",
        "amount",
        "probability",
        F.to_date("close_date").alias("close_date"),
        (F.col("stage") == "Closed Won").alias("is_won"),
        "owner",
        "last_modified",
    )


@dp.materialized_view(name="silver_sales_targets", comment="Monthly sales targets per region from Finance's Excel workbooks.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("valid_target", "target_amount > 0 AND month IS NOT NULL")
def silver_sales_targets():
    df = spark.read.table("bronze_excel_sales_targets").withColumn("month", F.to_date("month"))
    return latest_per_key(df, ["region", "month"], "_ingested_at").select("region", "month", "target_amount", "owner")


@dp.materialized_view(name="silver_orders", comment="ERP sales orders with revenue.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("valid_order_id", "order_id IS NOT NULL")
@dp.expect_or_drop("positive_quantity", "quantity > 0")
@dp.expect("known_status", "order_status IN ('OPEN', 'SHIPPED', 'CANCELLED')")
def silver_orders():
    df = spark.read.table("bronze_erp_orders")
    return latest_per_key(df, ["order_id"], "_ingested_at").select(
        "order_id",
        "account_id",
        "sku",
        "quantity",
        "unit_price",
        F.round(F.col("quantity") * F.col("unit_price"), 2).alias("revenue"),
        F.to_date("order_date").alias("order_date"),
        "warehouse_id",
        "order_status",
    )


# ---------------------------------------------------------------- Inventory
@dp.materialized_view(name="silver_inventory", comment="Latest ERP inventory position per warehouse and SKU.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("non_negative_on_hand", "on_hand_qty >= 0")
def silver_inventory():
    df = spark.read.table("bronze_erp_inventory").withColumn("snapshot_ts", F.to_timestamp("snapshot_ts"))
    return latest_per_key(df, ["warehouse_id", "sku"], "snapshot_ts").select(
        "warehouse_id", "sku", "on_hand_qty", "reorder_point", "snapshot_ts"
    )


# ---------------------------------------------------------------- Logistics
@dp.materialized_view(name="silver_shipments", comment="Shipments with transit time and on-time flags.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("valid_shipment_id", "shipment_id IS NOT NULL")
@dp.expect("delivered_after_ship", "delivered_date IS NULL OR delivered_date >= ship_date")
def silver_shipments():
    df = spark.read.table("bronze_logistics_shipments")
    df = latest_per_key(df, ["shipment_id"], "_ingested_at")
    return df.select(
        "shipment_id",
        "order_id",
        "carrier",
        "warehouse_id",
        F.to_date("ship_date").alias("ship_date"),
        F.to_date("promised_date").alias("promised_date"),
        F.to_date("delivered_date").alias("delivered_date"),
        "status",
        "freight_cost",
    ).withColumns(
        {
            "is_delivered": F.col("delivered_date").isNotNull(),
            "is_on_time": F.when(F.col("delivered_date").isNull(), None).otherwise(
                F.col("delivered_date") <= F.col("promised_date")
            ),
            "transit_days": F.datediff("delivered_date", "ship_date"),
        }
    )


# ---------------------------------------------------------------- Manufacturing
@dp.materialized_view(name="silver_machine_telemetry", comment="Validated hourly machine telemetry.", table_properties=SILVER_PROPS)
@dp.expect_or_drop("valid_reading", "machine_id IS NOT NULL AND reading_ts IS NOT NULL")
@dp.expect_or_drop("scrap_not_above_output", "units_scrapped <= units_produced")
@dp.expect("plausible_temperature", "temperature_c BETWEEN -20 AND 200")
def silver_machine_telemetry():
    df = spark.read.table("bronze_mfg_machine_telemetry").withColumn("reading_ts", F.to_timestamp("reading_ts"))
    return latest_per_key(df, ["machine_id", "reading_ts"], "_ingested_at").select(
        "reading_ts",
        F.to_date("reading_ts").alias("reading_date"),
        "plant_id",
        "machine_id",
        "status",
        "units_produced",
        "units_scrapped",
        "ideal_units_per_hour",
        "temperature_c",
        "vibration_mm_s",
    )
