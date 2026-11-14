"""Tests for the validation and risk rules in backend/check_data.py."""

import json

from backend.check_data import DATA_FILE, risk_group, validate

SUPPLIER = {"id": "S01", "name": "Test", "lead_time_days": 5, "minimum_order_quantity": 100}


def make_product(**changes):
    """A valid product. Pass keyword arguments to change any field."""
    product = {
        "id": "P001", "name": "Test flour", "unit": "kg",
        "current_stock": 1000, "avg_daily_usage": 100, "safety_stock": 200,
        "supplier_id": "S01", "on_order_quantity": 0,
    }
    product.update(changes)
    return product


def test_real_data_file_is_valid():
    data = json.loads(DATA_FILE.read_text())
    assert validate(data) == []


def test_validate_catches_unknown_supplier():
    data = {"suppliers": [SUPPLIER], "products": [make_product(supplier_id="S99")]}
    assert any("unknown supplier_id" in p for p in validate(data))


def test_validate_catches_bad_unit():
    data = {"suppliers": [SUPPLIER], "products": [make_product(unit="kgs")]}
    assert any("unit must be" in p for p in validate(data))


def test_risk_will_run_out():
    # 400 kg / 100 per day = 4 days, but delivery takes 5.
    assert risk_group(make_product(current_stock=400), SUPPLIER) == "will run out"


def test_risk_close_to_limit():
    # Lasts 6 days, but only 100 kg left at delivery (below safety stock of 200).
    assert risk_group(make_product(current_stock=600), SUPPLIER) == "close to limit"


def test_risk_ok():
    assert risk_group(make_product(current_stock=1000), SUPPLIER) == "ok"


def test_stock_on_order_counts():
    # Only 400 kg in stock, but 600 kg already on order -> fine.
    product = make_product(current_stock=400, on_order_quantity=600)
    assert risk_group(product, SUPPLIER) == "ok"
