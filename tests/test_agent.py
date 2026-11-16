"""Tests for the agent in backend/agent.py."""

import json
from datetime import date

from backend.agent import (
    COVERAGE_DAYS,
    quantity_needed,
    reorder_quantity,
    suggest_requisitions,
)
from backend.check_data import DATA_FILE

SUPPLIER = {"id": "S01", "name": "Test Mills", "lead_time_days": 5, "minimum_order_quantity": 100}
TODAY = date(2026, 11, 16)  # a fixed date, so delivery dates are predictable


def make_product(**changes):
    """An at-risk product: 400 kg lasts 4 days, but delivery takes 5. Change any field."""
    product = {
        "id": "P001", "name": "Test flour", "unit": "kg",
        "current_stock": 400, "avg_daily_usage": 100, "safety_stock": 200,
        "supplier_id": "S01", "on_order_quantity": 0,
    }
    product.update(changes)
    return product


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


def test_supplier_minimum_is_applied():
    supplier = dict(SUPPLIER, minimum_order_quantity=5000)
    assert reorder_quantity(make_product(), supplier) == 5000


def test_quantity_is_rounded_up():
    # (30 x 2.55) + 8 - 30 = 54.5 -> rounded up to 55
    product = make_product(avg_daily_usage=2.55, safety_stock=8, current_stock=30)
    assert quantity_needed(product) == 55


def test_quantity_needed_is_never_negative():
    assert quantity_needed(make_product(current_stock=100000)) == 0


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
        "expected_delivery_date": "2026-11-21",  # 16 Nov + 5 days
        "reason": draft["reason"],  # checked separately below
    }


def test_reason_is_two_sentences_with_real_numbers():
    data = {"suppliers": [SUPPLIER], "products": [make_product()]}
    reason = suggest_requisitions(data, today=TODAY)[0]["reason"]
    assert reason == (
        "Test flour has 400 kg available, enough for 4 days, but Test Mills needs 5 days "
        "to deliver. Ordering 2,800 kg brings stock up to 30 days of usage "
        "(100 kg per day) plus the 200 kg safety stock."
    )


def test_reason_mentions_supplier_minimum_when_it_applies():
    supplier = dict(SUPPLIER, minimum_order_quantity=5000)
    data = {"suppliers": [supplier], "products": [make_product()]}
    reason = suggest_requisitions(data, today=TODAY)[0]["reason"]
    assert "needs only 2,800 kg" in reason
    assert "minimum order of 5,000 kg" in reason


# ---------- With the real data ----------

def test_real_data_gives_5_high_and_3_medium_drafts():
    drafts = suggest_requisitions(load_real_data(), today=TODAY)
    urgencies = [d["urgency"] for d in drafts]
    assert urgencies == ["high"] * 5 + ["medium"] * 3


def test_real_data_rye_flour():
    drafts = suggest_requisitions(load_real_data(), today=TODAY)
    rye = next(d for d in drafts if d["product_id"] == "P003")
    # (30 x 120) + 300 - 420 = 3,480 kg
    assert rye["quantity"] == 3480
    assert rye["supplier_name"] == "Millbrook Grain Co."
    assert rye["expected_delivery_date"] == "2026-11-21"


def test_suggestions_do_not_change_the_data():
    data = load_real_data()
    before = json.dumps(data)
    suggest_requisitions(data, today=TODAY)
    assert json.dumps(data) == before
