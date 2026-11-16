"""Tests for the agent in backend/agent.py."""

import json
from datetime import date

from backend.agent import (
    COVERAGE_DAYS,
    PERISHABLE_COVERAGE_DAYS,
    amount_text,
    expected_delivery_date,
    is_plural,
    quantity_needed,
    reorder_quantity,
    suggest_requisitions,
)
from backend.check_data import DATA_FILE

SUPPLIER = {"id": "S01", "name": "Test Mills", "lead_time_days": 5}
TODAY = date(2026, 11, 16)  # a fixed Monday, so delivery dates are predictable


def make_product(**changes):
    """An at-risk product: 400 kg lasts 4 days, but delivery takes 5. Change any field."""
    product = {
        "id": "P001", "name": "Test flour", "unit": "kg",
        "current_stock": 400, "avg_daily_usage": 100, "safety_stock": 200,
        "min_order_quantity": 100, "perishable": False,
        "supplier_id": "S01", "on_order_quantity": 0,
    }
    product.update(changes)
    return product


def reason_for(product, supplier=SUPPLIER):
    data = {"suppliers": [supplier], "products": [product]}
    return suggest_requisitions(data, today=TODAY)[0]["reason"]


def load_real_data():
    return json.loads(DATA_FILE.read_text())


# ---------- The reorder formula ----------

def test_formula_uses_coverage_days():
    # (30 x 100) + 200 - 400 = 2,800
    assert COVERAGE_DAYS == 30
    assert quantity_needed(make_product()) == 2800


def test_stock_on_order_is_subtracted():
    # (30 x 100) + 200 - (400 + 500) = 2,300
    assert quantity_needed(make_product(on_order_quantity=500)) == 2300


def test_perishable_products_use_shorter_window():
    # (7 x 100) + 200 - 400 = 500
    assert PERISHABLE_COVERAGE_DAYS == 7
    assert quantity_needed(make_product(perishable=True)) == 500


def test_product_minimum_is_applied():
    assert reorder_quantity(make_product(min_order_quantity=5000)) == 5000


def test_minimum_does_not_lower_a_bigger_order():
    assert reorder_quantity(make_product(min_order_quantity=50)) == 2800


def test_quantity_is_rounded_up():
    # (30 x 2.55) + 8 - 30 = 54.5 -> rounded up to 55
    product = make_product(avg_daily_usage=2.55, safety_stock=8, current_stock=30)
    assert quantity_needed(product) == 55


def test_quantity_needed_is_never_negative():
    assert quantity_needed(make_product(current_stock=100000)) == 0


# ---------- Delivery dates ----------

def test_weekday_delivery_is_not_moved():
    assert expected_delivery_date(TODAY, 2) == date(2026, 11, 18)  # Wednesday


def test_saturday_delivery_moves_to_monday():
    assert expected_delivery_date(TODAY, 5) == date(2026, 11, 23)


def test_sunday_delivery_moves_to_monday():
    assert expected_delivery_date(TODAY, 6) == date(2026, 11, 23)


# ---------- Natural wording ----------

def test_is_plural():
    assert is_plural("Printed cake boxes")
    assert is_plural("Rolled oats")
    assert not is_plural("Rye flour")
    assert not is_plural("Pallet shrink-wrap film")
    assert not is_plural("Clear glass")  # ends in "ss", so singular


def test_plural_guess_is_right_for_every_real_product():
    plural_ids = {"P004", "P017", "P034", "P035", "P036", "P037", "P039", "P040"}
    for product in load_real_data()["products"]:
        assert is_plural(product["name"]) == (product["id"] in plural_ids), product["name"]


def test_amount_text_uses_natural_units():
    assert amount_text(420, make_product()) == "420 kg"
    assert amount_text(700, make_product(unit="litres")) == "700 litres"
    assert amount_text(1, make_product(unit="litres")) == "1 litre"
    assert amount_text(9600, make_product(unit="units", name="Printed cake boxes")) == "9,600 boxes"


# ---------- The drafts ----------

def test_one_draft_per_at_risk_product():
    data = {"suppliers": [SUPPLIER], "products": [
        make_product(id="P001"),                       # will run out
        make_product(id="P002", current_stock=600),    # close to limit
        make_product(id="P003", current_stock=10000),  # ok -> no draft
    ]}
    drafts = suggest_requisitions(data, today=TODAY)
    assert [d["product_id"] for d in drafts] == ["P001", "P002"]
    assert [d["urgency"] for d in drafts] == ["high", "medium"]


def test_draft_has_all_fields():
    data = {"suppliers": [SUPPLIER], "products": [make_product()]}
    draft = suggest_requisitions(data, today=TODAY)[0]
    assert draft == {
        "status": "draft",
        "product_id": "P001",
        "product_name": "Test flour",
        "supplier_id": "S01",
        "supplier_name": "Test Mills",
        "quantity": 2800,
        "unit": "kg",
        "urgency": "high",
        "expected_delivery_date": "2026-11-23",  # Mon 16 Nov + 5 days = Sat, moved to Mon
        "reason": draft["reason"],  # checked separately below
    }


# ---------- The reasons ----------

def test_reason_singular_product():
    assert reason_for(make_product()) == (
        "Test flour has 4 days of stock left (400 kg available), but Test Mills needs "
        "5 days to deliver. Ordering 2,800 kg brings stock up to 30 days of use at "
        "100 kg a day, plus the safety stock of 200 kg."
    )


def test_reason_plural_product_counted_in_units():
    product = make_product(name="Printed cake boxes", unit="units")
    assert reason_for(product) == (
        "Printed cake boxes have 4 days of stock left (400 boxes available), but Test Mills "
        "needs 5 days to deliver. Ordering 2,800 boxes brings stock up to 30 days of use "
        "at 100 boxes a day, plus the safety stock of 200 boxes."
    )


def test_reason_close_to_limit_plural():
    product = make_product(name="Printed bread bags", unit="units", current_stock=600)
    assert reason_for(product).startswith(
        "Printed bread bags have enough stock to last until a delivery could arrive in "
        "5 days, but they would be down to 100 bags by then, below the safety stock of 200 bags."
    )


def test_reason_mentions_minimum_when_it_applies():
    reason = reason_for(make_product(min_order_quantity=5000))
    assert reason.endswith(
        "Covering 30 days of use plus the safety stock of 200 kg needs only 2,800 kg, "
        "but the minimum order for test flour is 5,000 kg, so the order is raised to that."
    )


def test_reason_mentions_perishable():
    reason = reason_for(make_product(perishable=True))
    assert "7 days of use (kept short because it is perishable)" in reason


# ---------- With the real data ----------

def test_real_data_gives_5_high_and_3_medium_drafts():
    drafts = suggest_requisitions(load_real_data(), today=TODAY)
    urgencies = [d["urgency"] for d in drafts]
    assert urgencies == ["high"] * 5 + ["medium"] * 3


def test_real_data_rye_flour():
    drafts = suggest_requisitions(load_real_data(), today=TODAY)
    rye = next(d for d in drafts if d["product_id"] == "P003")
    # (30 x 120) + 300 - 420 = 3,480 kg, above the 1,000 kg minimum
    assert rye["quantity"] == 3480
    assert rye["supplier_name"] == "Millbrook Grain Co."
    assert rye["expected_delivery_date"] == "2026-11-23"


def test_real_data_fresh_yeast_uses_short_window_and_minimum():
    drafts = suggest_requisitions(load_real_data(), today=TODAY)
    yeast = next(d for d in drafts if d["product_id"] == "P027")
    # (7 x 18) + 25 - 45 = 106 kg, raised to the 120 kg minimum
    assert yeast["quantity"] == 120


def test_real_data_butter_is_perishable():
    drafts = suggest_requisitions(load_real_data(), today=TODAY)
    butter = next(d for d in drafts if d["product_id"] == "P018")
    # (7 x 210) + 200 - 260 = 1,410 kg, above the 250 kg minimum
    assert butter["quantity"] == 1410
    assert butter["urgency"] == "high"
    assert butter["expected_delivery_date"] == "2026-11-18"  # Mon + 2 days = Wednesday
    assert butter["reason"] == (
        "Unsalted butter has 1.2 days of stock left (260 kg available), but Greenpasture "
        "Dairy needs 2 days to deliver. Ordering 1,410 kg brings stock up to 7 days of use "
        "(kept short because it is perishable) at 210 kg a day, plus the safety stock of 200 kg."
    )


def test_suggestions_do_not_change_the_data():
    data = load_real_data()
    before = json.dumps(data)
    suggest_requisitions(data, today=TODAY)
    assert json.dumps(data) == before
