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

# Perishable products ("perishable": true in data.json) would spoil if we
# bought 30 days' worth, so they get this shorter window instead.
PERISHABLE_COVERAGE_DAYS = 7

# Suppliers don't deliver on these weekdays (Monday is 0, Sunday is 6).
# A delivery that would land on one of them moves to the next working day.
NO_DELIVERY_WEEKDAYS = {5, 6}  # Saturday and Sunday

# Which risk groups get a draft, and how urgent each one is.
# Products in any other group ("ok") get no draft.
URGENCY_BY_RISK_GROUP = {
    "will run out": "high",
    "close to limit": "medium",
}

# Sort order for the drafts: most urgent first.
URGENCY_RANK = {"high": 1, "medium": 2}


# ---------- Calculations ----------

def coverage_days(product):
    """How many days of usage a new order should cover for this product."""
    if product["perishable"]:
        return PERISHABLE_COVERAGE_DAYS
    return COVERAGE_DAYS


def quantity_needed(product):
    """
    The amount needed to reach the coverage days plus the safety stock:

        (coverage days x daily usage) + safety stock - available stock

    Rounded up to a whole number, and never below 0.
    """
    available = product["current_stock"] + product["on_order_quantity"]
    target = coverage_days(product) * product["avg_daily_usage"] + product["safety_stock"]
    needed = target - available
    # round() removes tiny computer rounding errors (like 3480.0000001)
    # so that math.ceil() (which rounds up) does not turn them into 3481.
    return max(math.ceil(round(needed, 6)), 0)


def reorder_quantity(product):
    """The quantity to order: what is needed, but at least the product's minimum order."""
    return max(quantity_needed(product), product["min_order_quantity"])


def expected_delivery_date(today, lead_time_days):
    """Today plus the lead time, moved forward if it lands on a no-delivery day."""
    delivery = today + timedelta(days=lead_time_days)
    while delivery.weekday() in NO_DELIVERY_WEEKDAYS:
        delivery += timedelta(days=1)
    return delivery


# ---------- Helpers for writing natural sentences ----------

def is_plural(name):
    """
    Guess whether a product name is plural from its last word:
    "Printed cake boxes" -> True, "Rye flour" -> False.
    Words ending in "ss" (like "glass") count as singular.
    """
    last_word = name.split()[-1].lower()
    return last_word.endswith("s") and not last_word.endswith("ss")


def format_number(value):
    """Make numbers easy to read: 3480 -> '3,480' and 3.5 -> '3.5'."""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.1f}"


def amount_text(value, product):
    """
    Write an amount with a natural unit:
        kg     -> "420 kg"
        litres -> "700 litres" (or "1 litre")
        units  -> "9,600 boxes" (the last word of the product name)
    """
    number = format_number(value)
    unit = product["unit"]
    if unit == "litres":
        return f"{number} litre" if value == 1 else f"{number} litres"
    if unit == "units":
        name = product["name"]
        noun = name.split()[-1].lower() if is_plural(name) else "units"
        return f"{number} {noun}"
    return f"{number} {unit}"


def days_text(value):
    """'1 day', '3.5 days', '5 days'."""
    return "1 day" if value == 1 else f"{format_number(value)} days"


def write_reason(product, supplier, group):
    """Write a two-sentence explanation using the product's real numbers."""
    name = product["name"]
    lower_name = name[0].lower() + name[1:]  # for use in the middle of a sentence

    # Words that change when the product name is plural.
    plural = is_plural(name)
    has = "have" if plural else "has"
    it_would = "they would" if plural else "it would"
    it_is = "they are" if plural else "it is"

    def amount(value):
        return amount_text(value, product)

    usage = product["avg_daily_usage"]
    safety = product["safety_stock"]
    available = product["current_stock"] + product["on_order_quantity"]
    lead_time = supplier["lead_time_days"]
    needed = quantity_needed(product)
    quantity = reorder_quantity(product)

    # Sentence 1: why this product needs attention.
    if group == "will run out":
        days_left = round(days_of_stock_left(product), 1)
        first = (f"{name} {has} {days_text(days_left)} of stock left ({amount(available)} available), "
                 f"but {supplier['name']} needs {days_text(lead_time)} to deliver.")
    else:  # "close to limit"
        left_at_delivery = available - usage * lead_time
        first = (f"{name} {has} enough stock to last until a delivery could arrive in "
                 f"{days_text(lead_time)}, but {it_would} be down to {amount(left_at_delivery)} "
                 f"by then, below the safety stock of {amount(safety)}.")

    # Sentence 2: why this quantity.
    window = f"{days_text(coverage_days(product))} of use"
    if product["perishable"]:
        window += f" (kept short because {it_is} perishable)"

    if quantity > needed:  # the minimum order pushed the quantity up
        second = (f"Covering {window} plus the safety stock of {amount(safety)} needs only "
                  f"{amount(needed)}, but the minimum order for {lower_name} is "
                  f"{amount(quantity)}, so the order is raised to that.")
    else:
        second = (f"Ordering {amount(quantity)} brings stock up to {window} at "
                  f"{amount(usage)} a day, plus the safety stock of {amount(safety)}.")

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

        delivery_date = expected_delivery_date(today, supplier["lead_time_days"])

        drafts.append({
            "status": "draft",
            "product_id": product["id"],
            "product_name": product["name"],
            "supplier_id": supplier["id"],
            "supplier_name": supplier["name"],
            "quantity": reorder_quantity(product),
            "unit": product["unit"],
            "urgency": URGENCY_BY_RISK_GROUP[group],
            "expected_delivery_date": delivery_date.isoformat(),  # e.g. "2026-11-23"
            "reason": write_reason(product, supplier, group),
        })

    # Sort so "high" drafts come before "medium" ones.
    drafts.sort(key=lambda draft: URGENCY_RANK[draft["urgency"]])
    return drafts
