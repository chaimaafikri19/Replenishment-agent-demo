"""Tests for the API in backend/main.py. Run with: pytest"""

import json

import pytest
from fastapi.testclient import TestClient

from backend import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    A test client that calls the API without starting a real server.
    Requisitions are saved to a temporary folder (tmp_path), so the tests
    never touch the real data/requisitions.json.
    """
    monkeypatch.setattr(main, "REQUISITIONS_FILE", tmp_path / "requisitions.json")
    return TestClient(main.app)


# ---------- GET /stock ----------

def test_stock_returns_all_products_with_calculated_fields(client):
    response = client.get("/stock")
    assert response.status_code == 200
    products = response.json()
    assert len(products) == 40
    for product in products:
        assert "days_of_stock_left" in product
        assert product["risk_group"] in ("will run out", "close to limit", "ok")


def test_stock_risk_group_counts(client):
    products = client.get("/stock").json()
    groups = [p["risk_group"] for p in products]
    assert groups.count("will run out") == 5
    assert groups.count("close to limit") == 3
    assert groups.count("ok") == 32


def test_stock_rye_flour_values(client):
    # Rye flour: 420 kg in stock, 120 kg used per day -> 3.5 days, supplier needs 5.
    products = client.get("/stock").json()
    rye = next(p for p in products if p["id"] == "P003")
    assert rye["days_of_stock_left"] == 3.5
    assert rye["risk_group"] == "will run out"


# ---------- GET /suppliers ----------

def test_suppliers_returns_all_six(client):
    response = client.get("/suppliers")
    assert response.status_code == 200
    assert len(response.json()) == 6


# ---------- GET /agent/suggestions ----------

def test_agent_suggestions_returns_drafts(client):
    response = client.get("/agent/suggestions")
    assert response.status_code == 200
    drafts = response.json()
    assert len(drafts) == 8
    assert all(d["status"] == "draft" for d in drafts)


def test_agent_suggestions_save_nothing(client):
    client.get("/agent/suggestions")
    assert not main.REQUISITIONS_FILE.exists()


def test_a_draft_can_be_confirmed_with_post_requisitions(client):
    # This is the "human in control" step: a person picks a draft and saves it.
    draft = client.get("/agent/suggestions").json()[0]
    response = client.post("/requisitions", json={
        "product_id": draft["product_id"],
        "quantity": draft["quantity"],
    })
    assert response.status_code == 201
    assert response.json()["quantity"] == draft["quantity"]


# ---------- POST /requisitions ----------

def test_create_requisition_returns_and_saves_record(client):
    response = client.post("/requisitions", json={"product_id": "P003", "quantity": 2000})
    assert response.status_code == 201
    record = response.json()
    assert record["id"] == "R0001"
    assert record["product_id"] == "P003"
    assert record["product_name"] == "Rye flour"
    assert record["quantity"] == 2000
    assert record["unit"] == "kg"

    # The record should also be in the file.
    saved = json.loads(main.REQUISITIONS_FILE.read_text())
    assert saved == [record]


def test_second_requisition_gets_next_id(client):
    client.post("/requisitions", json={"product_id": "P003", "quantity": 2000})
    response = client.post("/requisitions", json={"product_id": "P018", "quantity": 500})
    assert response.json()["id"] == "R0002"
    assert len(json.loads(main.REQUISITIONS_FILE.read_text())) == 2


def test_unknown_product_returns_404(client):
    response = client.post("/requisitions", json={"product_id": "P999", "quantity": 10})
    assert response.status_code == 404


@pytest.mark.parametrize("quantity", [0, -5])
def test_quantity_must_be_positive(client, quantity):
    response = client.post("/requisitions", json={"product_id": "P003", "quantity": quantity})
    assert response.status_code == 422


def test_missing_field_returns_422(client):
    response = client.post("/requisitions", json={"product_id": "P003"})
    assert response.status_code == 422


def test_failed_request_saves_nothing(client):
    client.post("/requisitions", json={"product_id": "P999", "quantity": 10})
    assert not main.REQUISITIONS_FILE.exists()
