"""Gold layer: business-ready KPIs for sales, logistics, inventory and manufacturing."""
from pyspark import pipelines as dp
from pyspark.sql import functions as F

GOLD_PROPS = {"quality": "gold"}


@dp.materialized_view(
    name="gold_sales_performance",
    comment="Monthly revenue (ERP), closed-won bookings (Salesforce) and target attainment (Excel) per region.",
    table_properties=GOLD_PROPS,
)
def gold_sales_performance():
    accounts = spark.read.table("silver_accounts").select("account_id", "region")

    revenue = (
        spark.read.table("silver_orders")
        .filter("order_status <> 'CANCELLED'")
        .join(accounts, "account_id")
        .groupBy("region", F.trunc("order_date", "month").alias("month"))
        .agg(F.sum("revenue").alias("orders_revenue"), F.countDistinct("order_id").alias("orders"))
    )
    bookings = (
        spark.read.table("silver_opportunities")
        .filter("is_won")
        .join(accounts, "account_id")
        .groupBy("region", F.trunc("close_date", "month").alias("month"))
        .agg(F.sum("amount").alias("closed_won_bookings"), F.count("*").alias("won_deals"))
    )
    targets = spark.read.table("silver_sales_targets").select("region", "month", "target_amount")

    return (
        revenue.join(bookings, ["region", "month"], "full_outer")
        .join(targets, ["region", "month"], "left")
        .fillna(0, subset=["orders_revenue", "orders", "closed_won_bookings", "won_deals"])
        .withColumn(
            "target_attainment_pct",
            F.when(F.col("target_amount") > 0, F.round(F.col("orders_revenue") / F.col("target_amount") * 100, 1)),
        )
    )


@dp.materialized_view(
    name="gold_delivery_performance",
    comment="On-time delivery rate, transit time and freight cost per carrier, warehouse and month.",
    table_properties=GOLD_PROPS,
)
def gold_delivery_performance():
    return (
        spark.read.table("silver_shipments")
        .groupBy("carrier", "warehouse_id", F.trunc("ship_date", "month").alias("ship_month"))
        .agg(
            F.count("*").alias("shipments"),
            F.sum(F.col("is_delivered").cast("int")).alias("delivered"),
            F.round(F.avg(F.col("is_on_time").cast("double")), 3).alias("on_time_rate"),
            F.round(F.avg("transit_days"), 1).alias("avg_transit_days"),
            F.round(F.sum("freight_cost"), 2).alias("total_freight_cost"),
            F.sum(F.when(F.col("is_delivered") & ~F.col("is_on_time"), 1).otherwise(0)).alias("late_shipments"),
            F.round(F.avg("freight_cost"), 2).alias("avg_freight_cost"),
        )
    )


@dp.materialized_view(
    name="gold_inventory_coverage",
    comment="Days of inventory cover per warehouse and SKU, based on the last 30 days of ERP demand.",
    table_properties=GOLD_PROPS,
)
def gold_inventory_coverage():
    orders = spark.read.table("silver_orders").filter("order_status <> 'CANCELLED'")
    latest_order_date = orders.agg(F.max("order_date").alias("max_date"))
    demand = (
        orders.crossJoin(latest_order_date)
        .filter(F.col("order_date") > F.date_sub("max_date", 30))
        .groupBy("warehouse_id", "sku")
        .agg((F.sum("quantity") / F.lit(30.0)).alias("avg_daily_demand"))
    )
    return (
        spark.read.table("silver_inventory")
        .join(demand, ["warehouse_id", "sku"], "left")
        .fillna(0.0, subset=["avg_daily_demand"])
        .withColumns(
            {
                "avg_daily_demand": F.round("avg_daily_demand", 2),
                "days_of_cover": F.when(
                    F.col("avg_daily_demand") > 0, F.round(F.col("on_hand_qty") / F.col("avg_daily_demand"), 1)
                ),
                "below_reorder_point": F.col("on_hand_qty") < F.col("reorder_point"),
            }
        )
    )


@dp.materialized_view(
    name="gold_machine_oee",
    comment="Daily Overall Equipment Effectiveness (availability x performance x quality) per machine.",
    table_properties=GOLD_PROPS,
)
def gold_machine_oee():
    daily = (
        spark.read.table("silver_machine_telemetry")
        .groupBy("plant_id", "machine_id", "reading_date")
        .agg(
            F.count("*").alias("planned_hours"),
            F.sum(F.when(F.col("status") == "RUNNING", 1).otherwise(0)).alias("run_hours"),
            F.sum(F.when(F.col("status") == "DOWN", 1).otherwise(0)).alias("down_hours"),
            F.sum("units_produced").alias("units_produced"),
            F.sum("units_scrapped").alias("units_scrapped"),
            F.max("ideal_units_per_hour").alias("ideal_units_per_hour"),
        )
    )
    availability = F.col("run_hours") / F.col("planned_hours")
    performance = F.when(
        F.col("run_hours") > 0,
        F.least(F.lit(1.0), F.col("units_produced") / (F.col("ideal_units_per_hour") * F.col("run_hours"))),
    ).otherwise(F.lit(0.0))
    quality = F.when(
        F.col("units_produced") > 0, (F.col("units_produced") - F.col("units_scrapped")) / F.col("units_produced")
    ).otherwise(F.lit(0.0))
    return daily.withColumns(
        {
            "availability": F.round(availability, 3),
            "performance": F.round(performance, 3),
            "quality": F.round(quality, 3),
            "oee": F.round(availability * performance * quality, 3),
        }
    )
