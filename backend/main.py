"""
FastAPI app for the Replenishment Assistant demo (all data is fictional).

Run it from the project folder with:
    uvicorn backend.main:app --reload
Then open http://127.0.0.1:8000/docs to try the endpoints in your browser.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Reuse the calculations from check_data.py instead of writing them twice.
from backend.check_data import days_of_stock_left, risk_group
from backend.agent import suggest_requisitions

# File locations, built relative to this file (same idea as in check_data.py).
DATA_FOLDER = Path(__file__).parent.parent / "data"
DATA_FILE = DATA_FOLDER / "data.json"
REQUISITIONS_FILE = DATA_FOLDER / "requisitions.json"

# Create the app. The title and description appear on the /docs page.
app = FastAPI(
    title="Replenishment Assistant",
    description="Demo API for a fictional food manufacturer's buyer.",
)


# ---------- Helper functions ----------

def load_data():
    """Read data.json. We read it on every request, so edits show up without a restart."""
    return json.loads(DATA_FILE.read_text())


def load_requisitions():
    """Read saved requisitions, or return an empty list if none have been saved yet."""
    if not REQUISITIONS_FILE.exists():
        return []
    return json.loads(REQUISITIONS_FILE.read_text())


def find_product(products, product_id):
    """Return the product with this id, or None if there isn't one."""
    for product in products:
        if product["id"] == product_id:
            return product
    return None


# ---------- What a POST /requisitions request must look like ----------

class RequisitionRequest(BaseModel):
    """
    The JSON body for POST /requisitions. FastAPI checks it automatically:
    a missing field, wrong type or quantity of 0 or less gets a 422 error.
    """
    product_id: str = Field(examples=["P003"])
    quantity: float = Field(gt=0, examples=[2000])  # gt=0 means "greater than 0"


# ---------- Endpoints ----------

@app.get("/stock")
def get_stock():
    """All products, each with days of stock left and a risk group."""
    data = load_data()
    suppliers_by_id = {s["id"]: s for s in data["suppliers"]}

    result = []
    for product in data["products"]:
        supplier = suppliers_by_id[product["supplier_id"]]
        item = dict(product)  # copy the product so we don't change the original
        item["days_of_stock_left"] = round(days_of_stock_left(product), 1)
        item["risk_group"] = risk_group(product, supplier)
        result.append(item)
    return result


@app.get("/suppliers")
def get_suppliers():
    """All suppliers."""
    return load_data()["suppliers"]


@app.get("/agent/suggestions")
def get_agent_suggestions():
    """
    Draft requisitions for every at-risk product, most urgent first.
    Nothing is saved here: a person confirms a draft by sending its
    product_id and quantity to POST /requisitions.
    """
    return suggest_requisitions(load_data())


@app.post("/requisitions", status_code=201)  # 201 means "created"
def create_requisition(request: RequisitionRequest):
    """Save a request to reorder a product and return the saved record."""
    data = load_data()
    product = find_product(data["products"], request.product_id)
    if product is None:
        # 404 means "not found". FastAPI turns this into a JSON error response.
        raise HTTPException(status_code=404, detail=f"Product '{request.product_id}' not found")

    requisitions = load_requisitions()
    record = {
        "id": f"R{len(requisitions) + 1:04d}",  # R0001, R0002, ...
        "product_id": product["id"],
        "product_name": product["name"],
        "quantity": request.quantity,
        "unit": product["unit"],
        "supplier_id": product["supplier_id"],
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }

    # Add the new record and write the whole list back to the file.
    requisitions.append(record)
    REQUISITIONS_FILE.write_text(json.dumps(requisitions, indent=2))
    return record
