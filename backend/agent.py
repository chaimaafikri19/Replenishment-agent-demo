"""
The replenishment "agent": looks at every product and drafts a requisition
for each one that is at risk.

It only SUGGESTS. It never saves anything. A person must confirm each draft
by sending it to POST /requisitions, so a human stays in control.

There is no external AI yet: each reason is written from a fixed template
filled in with the real numbers.
"""

import math
from datetime import date, timedelta

from backend.check_data import days_of_stock_left, risk_group

# ---------- Settings: change these to tune the agent ----------

# A new order should bring stock up to this many days of average usage
# (plus the safety stock).
COVERAGE_DAYS = 30

# Which risk groups get a draft, and how urgent each one is.
# Products in any other group ("ok") get no draft.
URGENCY_BY_RISK_GROUP = {
    "will run out": "high",
    "close to limit": "medium",
}

# Sort order for the drafts: most urgent first.
URGENCY_RANK = {"high": 1, "medium": 2}


# ---------- Calculations ----------

def quantity_needed(product):
    """
    The amount needed to reach COVERAGE_DAYS of usage plus the safety stock:

        (COVERAGE_DAYS x daily usage) + safety stock - available stock

    Rounded up to a whole number, and never below 0.
    """
    available = product["current_stock"] + product["on_order_quantity"]
    target = COVERAGE_DAYS * product["avg_daily_usage"] + product["safety_stock"]
    needed = target - available
    # round() removes tiny computer rounding errors (like 3480.0000001)
    # so that math.ceil() (which rounds up) does not turn them into 3481.
    return max(math.ceil(round(needed, 6)), 0)


def reorder_quantity(product, supplier):
    """The quantity to order: what is needed, but at least the supplier's minimum."""
    return max(quantity_needed(product), supplier["minimum_order_quantity"])


def format_number(value):
    """Make numbers easy to read: 3480 -> '3,480' and 3.5 -> '3.5'."""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.1f}"


def write_reason(product, supplier, group):
    """Write a two-sentence explanation using the product's real numbers."""
    n = format_number  # short name, to keep the sentences below readable
    name = product["name"]
    unit = product["unit"]
    usage = product["avg_daily_usage"]
    safety = product["safety_stock"]
    available = product["current_stock"] + product["on_order_quantity"]
    lead_time = supplier["lead_time_days"]
    needed = quantity_needed(product)
    quantity = reorder_quantity(product, supplier)

    # Sentence 1: why this product needs attention.
    if group == "will run out":
        days_left = round(days_of_stock_left(product), 1)
        first = (f"{name} has {n(available)} {unit} available, enough for {n(days_left)} days, "
                 f"but {supplier['name']} needs {lead_time} days to deliver.")
    else:  # "close to limit"
        left_at_delivery = available - usage * lead_time
        first = (f"{name} has {n(available)} {unit} available, but by the time a delivery "
                 f"could arrive in {lead_time} days it would be down to "
                 f"{n(left_at_delivery)} {unit}, below the {n(safety)} {unit} safety stock.")

    # Sentence 2: why this quantity.
    if quantity > needed:  # the supplier's minimum order pushed the quantity up
        second = (f"Covering {COVERAGE_DAYS} days plus safety stock needs only "
                  f"{n(needed)} {unit}, but {supplier['name']} has a minimum order of "
                  f"{n(quantity)} {unit}, so the order is raised to that.")
    else:
        second = (f"Ordering {n(quantity)} {unit} brings stock up to {COVERAGE_DAYS} days "
                  f"of usage ({n(usage)} {unit} per day) plus the {n(safety)} {unit} safety stock.")

    return f"{first} {second}"


# ---------- The main function ----------

def suggest_requisitions(data, today=None):
    """
    Return a list of draft requisitions, most urgent first.
    `today` can be passed in by tests, so the delivery dates are predictable.
    """
    if today is None:
        today = date.today()

    suppliers_by_id = {s["id"]: s for s in data["suppliers"]}
    drafts = []

    for product in data["products"]:
        supplier = suppliers_by_id[product["supplier_id"]]
        group = risk_group(product, supplier)
        if group not in URGENCY_BY_RISK_GROUP:
            continue  # this product is fine: skip to the next one

        # If ordered today, the delivery arrives after the supplier's lead time.
        delivery_date = today + timedelta(days=supplier["lead_time_days"])

        drafts.append({
            "status": "draft",
            "product_id": product["id"],
            "product_name": product["name"],
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "quantity": reorder_quantity(product, supplier),
            "unit": product["unit"],
            "urgency": URGENCY_BY_RISK_GROUP[group],
            "expected_delivery_date": delivery_date.isoformat(),  # e.g. "2026-11-21"
            "reason": write_reason(product, supplier, group),
        })

    # Sort so "high" drafts come before "medium" ones.
    drafts.sort(key=lambda draft: URGENCY_RANK[draft["urgency"]])
    return drafts
