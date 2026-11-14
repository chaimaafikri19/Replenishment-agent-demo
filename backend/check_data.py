"""
Checks that data/data.json is valid and prints how many products
fall into each risk group.

Run it from the project folder with:
    python3 backend/check_data.py
"""

import json
import sys
from pathlib import Path

# Build the path to data/data.json relative to this file,
# so the script works no matter which folder you run it from.
DATA_FILE = Path(__file__).parent.parent / "data" / "data.json"

ALLOWED_UNITS = {"kg", "litres", "units"}

# Fields every supplier and product must have, and the type each one should be.
# (int, float) means "any number".
SUPPLIER_FIELDS = {
    "id": str,
    "name": str,
    "lead_time_days": (int, float),
    "minimum_order_quantity": (int, float),
}
PRODUCT_FIELDS = {
    "id": str,
    "name": str,
    "unit": str,
    "current_stock": (int, float),
    "avg_daily_usage": (int, float),
    "safety_stock": (int, float),
    "supplier_id": str,
    "on_order_quantity": (int, float),
}


def check_fields(item, fields, label):
    """Return a list of problems with one supplier or product."""
    problems = []
    for field, expected_type in fields.items():
        if field not in item:
            problems.append(f"{label}: missing field '{field}'")
        elif not isinstance(item[field], expected_type) or isinstance(item[field], bool):
            problems.append(f"{label}: '{field}' has the wrong type")
        elif expected_type == (int, float) and item[field] < 0:
            problems.append(f"{label}: '{field}' must not be negative")
    return problems


def validate(data):
    """Return a list of all problems found in the data (empty list = valid)."""
    problems = []

    # Check suppliers and remember their ids.
    supplier_ids = set()
    for supplier in data.get("suppliers", []):
        label = f"Supplier {supplier.get('id', '?')}"
        problems += check_fields(supplier, SUPPLIER_FIELDS, label)
        if supplier.get("id") in supplier_ids:
            problems.append(f"{label}: duplicate id")
        supplier_ids.add(supplier.get("id"))

    # Check products.
    product_ids = set()
    for product in data.get("products", []):
        label = f"Product {product.get('id', '?')}"
        problems += check_fields(product, PRODUCT_FIELDS, label)
        if product.get("id") in product_ids:
            problems.append(f"{label}: duplicate id")
        product_ids.add(product.get("id"))
        if product.get("unit") not in ALLOWED_UNITS:
            problems.append(f"{label}: unit must be one of {sorted(ALLOWED_UNITS)}")
        if product.get("avg_daily_usage") == 0:
            problems.append(f"{label}: avg_daily_usage must be greater than 0")
        if product.get("supplier_id") not in supplier_ids:
            problems.append(f"{label}: unknown supplier_id '{product.get('supplier_id')}'")

    if not data.get("suppliers"):
        problems.append("No suppliers found")
    if not data.get("products"):
        problems.append("No products found")
    return problems


def risk_group(product, supplier):
    """
    Put a product into one of three risk groups.

    - "will run out":   stock (including what is already on order) lasts
                        fewer days than the supplier needs to deliver.
    - "close to limit": stock lasts until delivery, but would drop below
                        the safety stock before the delivery arrives.
    - "ok":             everything else.
    """
    available = product["current_stock"] + product["on_order_quantity"]
    usage = product["avg_daily_usage"]
    lead_time = supplier["lead_time_days"]

    days_of_cover = available / usage
    stock_left_at_delivery = available - usage * lead_time

    if days_of_cover < lead_time:
        return "will run out"
    if stock_left_at_delivery < product["safety_stock"]:
        return "close to limit"
    return "ok"


def main():
    # 1. Load the file. Stop with a clear message if it is not valid JSON.
    try:
        data = json.loads(DATA_FILE.read_text())
    except FileNotFoundError:
        sys.exit(f"Could not find {DATA_FILE}")
    except json.JSONDecodeError as error:
        sys.exit(f"data.json is not valid JSON: {error}")

    # 2. Check the contents.
    problems = validate(data)
    if problems:
        print("data.json has problems:")
        for problem in problems:
            print("  -", problem)
        sys.exit(1)
    print(f"data.json is valid: {len(data['suppliers'])} suppliers, "
          f"{len(data['products'])} products.\n")

    # 3. Sort every product into a risk group.
    suppliers_by_id = {s["id"]: s for s in data["suppliers"]}
    groups = {"will run out": [], "close to limit": [], "ok": []}
    for product in data["products"]:
        supplier = suppliers_by_id[product["supplier_id"]]
        groups[risk_group(product, supplier)].append(product)

    # 4. Print the counts, and list the products that need attention.
    for name, products in groups.items():
        print(f"{name}: {len(products)}")
        if name != "ok":
            for p in products:
                print(f"    {p['id']}  {p['name']}")


if __name__ == "__main__":
    main()
