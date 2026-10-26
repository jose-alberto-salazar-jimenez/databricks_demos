"""Deterministic generators that simulate the demo's source systems.

Pure Python (standard library only) so the logic can be unit tested in CI
without Spark or a Databricks workspace.

Simulated sources:
  * Salesforce   -> accounts, opportunities (JSON, CRM style API extracts)
  * Excel        -> yearly sales targets per region (xlsx uploaded by Finance)
  * ERP          -> sales orders and inventory snapshots (CSV exports)
  * Logistics    -> shipments from the carrier / TMS platform (JSON)
  * Manufacturing-> hourly machine telemetry from plant IoT gateways (JSON)
"""
from __future__ import annotations

import random
from datetime import date, datetime, timedelta

REGIONS = ["NORTH_AMERICA", "LATAM", "EMEA", "APAC"]
REGION_WAREHOUSE = {
    "NORTH_AMERICA": "WH-DAL",
    "LATAM": "WH-MEX",
    "EMEA": "WH-ROT",
    "APAC": "WH-SIN",
}
WAREHOUSES = list(REGION_WAREHOUSE.values())
INDUSTRIES = ["Automotive", "Food & Beverage", "Chemicals", "Energy", "Pharma", "Mining"]
NAME_PREFIX = ["Acme", "Globex", "Initech", "Umbrella", "Stark", "Wayne", "Tyrell", "Cyberdyne"]
NAME_SUFFIX = ["Industries", "Manufacturing", "Holdings", "Logistics", "Group", "Corp"]
OWNERS = ["a.garcia", "j.smith", "m.rossi", "k.tanaka", "l.muller"]

PRODUCTS = [
    {"sku": "SKU-1001", "product_name": "Industrial Pump", "category": "Pumps", "list_price": 1250.0},
    {"sku": "SKU-1002", "product_name": "Hydraulic Valve", "category": "Valves", "list_price": 340.0},
    {"sku": "SKU-1003", "product_name": "Servo Motor", "category": "Motors", "list_price": 890.0},
    {"sku": "SKU-1004", "product_name": "PLC Controller", "category": "Controls", "list_price": 2100.0},
    {"sku": "SKU-1005", "product_name": "Conveyor Belt 10m", "category": "Conveyors", "list_price": 3600.0},
    {"sku": "SKU-1006", "product_name": "Pressure Sensor", "category": "Sensors", "list_price": 120.0},
    {"sku": "SKU-1007", "product_name": "Gearbox", "category": "Motors", "list_price": 760.0},
    {"sku": "SKU-1008", "product_name": "Safety Relay", "category": "Controls", "list_price": 95.0},
]
PRICE_BY_SKU = {p["sku"]: p["list_price"] for p in PRODUCTS}

CARRIERS = ["DHL", "FedEx", "Maersk", "UPS"]
PLANTS = {
    "PLANT-MTY": ["MTY-CNC-01", "MTY-CNC-02", "MTY-ASM-01"],
    "PLANT-STU": ["STU-CNC-01", "STU-PRS-01", "STU-ASM-01"],
}
IDEAL_UNITS_PER_HOUR = {"CNC": 40, "ASM": 60, "PRS": 120}

OPPORTUNITY_STAGES = {
    "Prospecting": 10,
    "Qualification": 25,
    "Proposal": 50,
    "Negotiation": 75,
    "Closed Won": 100,
    "Closed Lost": 0,
}
ORDER_STATUSES = ["OPEN", "SHIPPED", "CANCELLED"]
MACHINE_STATUSES = ["RUNNING", "IDLE", "DOWN"]


def _iso(ts: datetime) -> str:
    return ts.replace(microsecond=0).isoformat()


def generate_accounts(as_of: datetime, n: int = 40, seed: int = 7) -> list[dict]:
    """Salesforce Account extract. A stable master list (same seed -> same accounts)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        rows.append(
            {
                "account_id": f"001A{i:05d}",
                "account_name": f"{rng.choice(NAME_PREFIX)} {rng.choice(NAME_SUFFIX)} {i}",
                "industry": rng.choice(INDUSTRIES),
                "region": REGIONS[i % len(REGIONS)],
                "annual_revenue": round(rng.uniform(5e6, 5e8), 2),
                "created_date": (date(2024, 1, 1) + timedelta(days=rng.randint(0, 600))).isoformat(),
                "last_modified": _iso(as_of),
            }
        )
    return rows


def generate_opportunities(accounts: list[dict], as_of: datetime, n: int = 60, seed: int = 1) -> list[dict]:
    """Salesforce Opportunity extract for one incremental batch."""
    rng = random.Random(seed)
    batch = as_of.strftime("%Y%m%d%H%M%S")
    rows = []
    for i in range(n):
        account = rng.choice(accounts)
        stage = rng.choice(list(OPPORTUNITY_STAGES))
        close_date = as_of.date() + timedelta(days=rng.randint(-60, 60))
        rows.append(
            {
                "opportunity_id": f"006{batch}{i:04d}",
                "account_id": account["account_id"],
                "opportunity_name": f"{account['account_name']} - {rng.choice(PRODUCTS)['category']} deal",
                "stage": stage,
                "amount": round(rng.uniform(5_000, 250_000), 2),
                "probability": OPPORTUNITY_STAGES[stage],
                "close_date": close_date.isoformat(),
                "owner": rng.choice(OWNERS),
                "last_modified": _iso(as_of),
            }
        )
    return rows


def generate_orders(accounts: list[dict], as_of: datetime, n: int = 200, seed: int = 2) -> list[dict]:
    """ERP sales order export (one line per order) for one incremental batch."""
    rng = random.Random(seed)
    batch = as_of.strftime("%Y%m%d%H%M%S")
    rows = []
    for i in range(n):
        account = rng.choice(accounts)
        product = rng.choice(PRODUCTS)
        rows.append(
            {
                "order_id": f"SO-{batch}-{i:05d}",
                "account_id": account["account_id"],
                "sku": product["sku"],
                "quantity": rng.randint(1, 25),
                "unit_price": round(product["list_price"] * rng.uniform(0.85, 1.0), 2),
                "order_date": (as_of.date() - timedelta(days=rng.randint(0, 29))).isoformat(),
                "warehouse_id": REGION_WAREHOUSE[account["region"]],
                "order_status": rng.choices(ORDER_STATUSES, weights=[30, 65, 5])[0],
            }
        )
    return rows


def generate_inventory(as_of: datetime, seed: int = 3) -> list[dict]:
    """ERP inventory snapshot: one row per warehouse x SKU."""
    rng = random.Random(seed)
    return [
        {
            "snapshot_ts": _iso(as_of),
            "warehouse_id": wh,
            "sku": p["sku"],
            "on_hand_qty": rng.randint(0, 600),
            "reorder_point": rng.choice([50, 75, 100, 150]),
        }
        for wh in WAREHOUSES
        for p in PRODUCTS
    ]


def generate_shipments(orders: list[dict], as_of: datetime, seed: int = 4) -> list[dict]:
    """Logistics / TMS shipments for every non-cancelled order."""
    rng = random.Random(seed)
    rows = []
    for o in orders:
        if o["order_status"] == "CANCELLED":
            continue
        ship_date = date.fromisoformat(o["order_date"]) + timedelta(days=rng.randint(0, 2))
        promised = ship_date + timedelta(days=rng.randint(3, 7))
        delivered = promised + timedelta(days=rng.choice([-2, -1, 0, 0, 0, 1, 2, 4]))
        is_delivered = delivered <= as_of.date()
        rows.append(
            {
                "shipment_id": f"SH-{o['order_id'][3:]}",
                "order_id": o["order_id"],
                "carrier": rng.choice(CARRIERS),
                "warehouse_id": o["warehouse_id"],
                "ship_date": ship_date.isoformat(),
                "promised_date": promised.isoformat(),
                "delivered_date": delivered.isoformat() if is_delivered else None,
                "status": "DELIVERED" if is_delivered else "IN_TRANSIT",
                "freight_cost": round(rng.uniform(40, 900), 2),
            }
        )
    return rows


def generate_machine_telemetry(as_of: datetime, hours: int = 24, seed: int = 5) -> list[dict]:
    """Hourly IoT readings per machine for the `hours` before `as_of`."""
    rng = random.Random(seed)
    start = as_of.replace(minute=0, second=0, microsecond=0) - timedelta(hours=hours)
    rows = []
    for plant, machines in PLANTS.items():
        for machine in machines:
            ideal = IDEAL_UNITS_PER_HOUR[machine.split("-")[1]]
            for h in range(hours):
                status = rng.choices(MACHINE_STATUSES, weights=[85, 10, 5])[0]
                produced = int(ideal * rng.uniform(0.7, 1.0)) if status == "RUNNING" else 0
                scrapped = int(produced * rng.uniform(0.0, 0.06))
                rows.append(
                    {
                        "reading_ts": _iso(start + timedelta(hours=h)),
                        "plant_id": plant,
                        "machine_id": machine,
                        "status": status,
                        "units_produced": produced,
                        "units_scrapped": scrapped,
                        "ideal_units_per_hour": ideal,
                        "temperature_c": round(rng.uniform(35, 85), 1),
                        "vibration_mm_s": round(rng.uniform(0.5, 9.0), 2),
                    }
                )
    return rows


def generate_sales_targets(year: int, seed: int = 6) -> list[dict]:
    """Finance's Excel sales targets: one row per region and month."""
    rng = random.Random(seed + year)
    return [
        {
            "region": region,
            "month": date(year, m, 1).isoformat(),
            "target_amount": float(round(rng.uniform(150_000, 450_000), -3)),
            "owner": "finance.planning",
        }
        for region in REGIONS
        for m in range(1, 13)
    ]
