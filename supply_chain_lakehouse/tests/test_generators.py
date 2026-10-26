"""Unit tests for the simulated source generators (run in CI on every pull request)."""
from datetime import date, datetime

import pytest

from supply_chain_lakehouse import generators as g

AS_OF = datetime(2026, 10, 26, 6, 0, 0)


@pytest.fixture(scope="module")
def accounts():
    return g.generate_accounts(as_of=AS_OF)


@pytest.fixture(scope="module")
def orders(accounts):
    return g.generate_orders(accounts, as_of=AS_OF, seed=123)


def test_accounts_are_stable_master_data(accounts):
    again = g.generate_accounts(as_of=AS_OF)
    assert [a["account_id"] for a in accounts] == [a["account_id"] for a in again]
    assert len({a["account_id"] for a in accounts}) == len(accounts)
    assert {a["region"] for a in accounts} == set(g.REGIONS)


def test_opportunities_reference_known_accounts(accounts):
    opps = g.generate_opportunities(accounts, as_of=AS_OF, seed=1)
    account_ids = {a["account_id"] for a in accounts}
    assert all(o["account_id"] in account_ids for o in opps)
    assert all(o["probability"] == g.OPPORTUNITY_STAGES[o["stage"]] for o in opps)
    assert all(o["amount"] > 0 for o in opps)


def test_orders_are_valid(orders):
    assert len({o["order_id"] for o in orders}) == len(orders)
    for o in orders:
        assert o["quantity"] > 0
        assert o["order_status"] in g.ORDER_STATUSES
        assert o["warehouse_id"] in g.WAREHOUSES
        # discounts never exceed 15% of list price
        assert 0.85 * g.PRICE_BY_SKU[o["sku"]] - 0.01 <= o["unit_price"] <= g.PRICE_BY_SKU[o["sku"]]
        assert date.fromisoformat(o["order_date"]) <= AS_OF.date()


def test_inventory_covers_every_warehouse_and_sku():
    inventory = g.generate_inventory(as_of=AS_OF)
    assert len(inventory) == len(g.WAREHOUSES) * len(g.PRODUCTS)
    assert all(row["on_hand_qty"] >= 0 for row in inventory)


def test_shipments_skip_cancelled_orders_and_have_consistent_dates(orders):
    shipments = g.generate_shipments(orders, as_of=AS_OF)
    cancelled = {o["order_id"] for o in orders if o["order_status"] == "CANCELLED"}
    assert not cancelled & {s["order_id"] for s in shipments}
    for s in shipments:
        assert s["promised_date"] > s["ship_date"]
        if s["status"] == "DELIVERED":
            assert s["delivered_date"] is not None
            assert date.fromisoformat(s["delivered_date"]) <= AS_OF.date()
        else:
            assert s["delivered_date"] is None


def test_machine_telemetry_is_physically_plausible():
    readings = g.generate_machine_telemetry(as_of=AS_OF, hours=24)
    machines = sum(len(m) for m in g.PLANTS.values())
    assert len(readings) == machines * 24
    for r in readings:
        assert 0 <= r["units_scrapped"] <= r["units_produced"] <= r["ideal_units_per_hour"]
        if r["status"] != "RUNNING":
            assert r["units_produced"] == 0


def test_sales_targets_cover_every_region_and_month():
    targets = g.generate_sales_targets(2026)
    assert len(targets) == len(g.REGIONS) * 12
    assert {t["month"][:4] for t in targets} == {"2026"}
    assert all(t["target_amount"] > 0 for t in targets)
