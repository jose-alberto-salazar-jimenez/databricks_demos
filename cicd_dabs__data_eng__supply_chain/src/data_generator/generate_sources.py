# Databricks notebook source
# MAGIC %md
# MAGIC # Generate simulated source data
# MAGIC
# MAGIC Lands one incremental batch per run in the Unity Catalog landing volume, mimicking how each source system delivers data:
# MAGIC
# MAGIC | Source system | Domain | Folder | Format |
# MAGIC | --- | --- | --- | --- |
# MAGIC | Salesforce | Sales (CRM) | `salesforce/accounts`, `salesforce/opportunities` | JSON lines |
# MAGIC | Excel (Finance) | Sales targets | `excel/sales_targets` | xlsx (one file per year) |
# MAGIC | ERP | Orders and inventory | `erp/orders`, `erp/inventory` | CSV |
# MAGIC | Logistics TMS | Shipments | `logistics/shipments` | JSON lines |
# MAGIC | Plant IoT gateways | Manufacturing | `manufacturing/telemetry` | JSON lines |

# COMMAND ----------

# MAGIC %pip install openpyxl==3.1.5 --quiet

# COMMAND ----------

import csv
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

import pandas as pd

dbutils.widgets.text("catalog", "dev_demo")
dbutils.widgets.text("schema", "supply_chain")
dbutils.widgets.text("volume", "landing")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
base_path = f"/Volumes/{catalog}/{schema}/{volume}"

# Make the shared package in src/ importable (this notebook lives in src/data_generator/).
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))
from supply_chain_sim import generators as g  # noqa: E402

as_of = datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)
stamp = as_of.strftime("%Y%m%dT%H%M%SZ")
seed = int(as_of.timestamp())
print(f"Landing batch {stamp} into {base_path}")

# COMMAND ----------

def write_jsonl(folder: str, rows: list[dict]) -> str:
    os.makedirs(f"{base_path}/{folder}", exist_ok=True)
    path = f"{base_path}/{folder}/{stamp}.json"
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    return path


def write_csv(folder: str, rows: list[dict]) -> str:
    os.makedirs(f"{base_path}/{folder}", exist_ok=True)
    path = f"{base_path}/{folder}/{stamp}.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_excel_targets(year: int) -> str | None:
    """Finance uploads one workbook per year; only land it if it is not there yet."""
    folder = f"{base_path}/excel/sales_targets"
    os.makedirs(folder, exist_ok=True)
    path = f"{folder}/sales_targets_{year}.xlsx"
    if os.path.exists(path):
        return None
    df = pd.DataFrame(g.generate_sales_targets(year))
    # Write locally first, then copy: xlsx writers need random access, volumes are write-once streams.
    with tempfile.TemporaryDirectory() as tmp:
        local = os.path.join(tmp, os.path.basename(path))
        df.to_excel(local, sheet_name="targets", index=False)
        shutil.copy(local, path)
    return path

# COMMAND ----------

accounts = g.generate_accounts(as_of=as_of)
opportunities = g.generate_opportunities(accounts, as_of=as_of, seed=seed)
orders = g.generate_orders(accounts, as_of=as_of, seed=seed + 1)
inventory = g.generate_inventory(as_of=as_of, seed=seed + 2)
shipments = g.generate_shipments(orders, as_of=as_of, seed=seed + 3)
telemetry = g.generate_machine_telemetry(as_of=as_of, seed=seed + 4)

written = {
    "salesforce/accounts": write_jsonl("salesforce/accounts", accounts),
    "salesforce/opportunities": write_jsonl("salesforce/opportunities", opportunities),
    "erp/orders": write_csv("erp/orders", orders),
    "erp/inventory": write_csv("erp/inventory", inventory),
    "logistics/shipments": write_jsonl("logistics/shipments", shipments),
    "manufacturing/telemetry": write_jsonl("manufacturing/telemetry", telemetry),
}
for year in sorted({as_of.year, (as_of - timedelta(days=30)).year}):
    excel_path = write_excel_targets(year)
    if excel_path:
        written[f"excel/sales_targets/{year}"] = excel_path

counts = {
    "accounts": len(accounts),
    "opportunities": len(opportunities),
    "orders": len(orders),
    "inventory": len(inventory),
    "shipments": len(shipments),
    "telemetry": len(telemetry),
}
print(json.dumps({"batch": stamp, "rows": counts, "files": written}, indent=2))
