"""
Extracts data for the Sales module's three pages:
  - sales/hot_codes.html    <- data/sales/hot_codes.json
  - sales/holds_sheet.html  <- data/sales/holds_sheet.json
  - sales/daily_orders.html <- data/sales/daily_orders.json

Mirrors the SQL in surgicentral/sales/routes.py:

  hot_codes(): products (is_active) LEFT JOIN inventory_lots (main/short_dated
    qty per ref) LEFT JOIN inventory_holds (regular-approved-unexpired qty,
    strategic-approved qty minus fulfilled), ordered by sku.

  holds_sheet(): inventory_holds LEFT JOIN products (name), ordered by
    created_at DESC. status_f is a query-string filter in the real route
    (active/released/all) -- reproduced client-side in JS over the full set
    since this is only 5 rows.

  daily_orders(): outbound_orders, ordered by order_date DESC, daily_order_number.
    Only 32 rows total -- embedded in full, no cap needed.

Frozen "today"/"NOW()" for the hot_codes expires_at > NOW() comparison:
2026-07-23 (the CSV dump date), matching the convention used by the other
extraction scripts in this repo (e.g. suppliers_extract.py).

Note on "Sophic == wholesale" reclassification (per CLAUDE.md domain rule):
checked products.csv, sales_history.csv, and sku_map.csv for "Sophic" in the
manufacturer/brand columns actually displayed by these three Sales pages --
zero matches. The columns that do contain literal "Sophic" strings
(inventory_lots.vend, outbound_scans.vend, purchase_orders.supplier) are not
selected by sales/routes.py and are not shown on any Sales page, so no
substitution logic applies here. (It may still matter for Procurement/
Warehouse modules, which do surface vendor/supplier fields -- out of scope
for this agent.)

Source CSVs (read-only, never copied into Clone/):
  products.csv, inventory_lots.csv, inventory_holds.csv, outbound_orders.csv
"""
import csv
import json
import os
from datetime import date, datetime

RAW_DIR = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT_DIR = r"C:\users\gary\surgi_central\Clone\data\sales"

TODAY = date(2026, 7, 23)


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_bool(v):
    return str(v).strip().lower() in ("t", "true", "1", "yes")


def to_float(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_date_str(v):
    v = (v or "").strip()
    if not v:
        return None
    return v[:10]  # 'YYYY-MM-DD HH:MM:SS+00' or 'YYYY-MM-DD' -> date part


def parse_date_loose(v):
    """Parse a date string that may have an out-of-range/typo'd year
    (real data has one buyback item expiration of '0027-05-29' elsewhere;
    inventory dates here are all sane, but stay defensive)."""
    d = to_date_str(v)
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except ValueError:
        return None


# ── Hot Codes ─────────────────────────────────────────────────────────────────

def build_hot_codes():
    products = read_csv("products.csv")
    lots = read_csv("inventory_lots.csv")
    holds = read_csv("inventory_holds.csv")

    main_qty = {}
    short_dated_qty = {}
    for lot in lots:
        ref = lot["ref"]
        qty = to_float(lot["qty_on_hand"]) or 0
        if lot["zone"] == "main":
            main_qty[ref] = main_qty.get(ref, 0) + qty
        elif lot["zone"] == "short_dated":
            short_dated_qty[ref] = short_dated_qty.get(ref, 0) + qty

    h_reg = {}  # regular, approved, unexpired -> sum(qty)
    h_str = {}  # strategic, approved -> sum(qty - fulfilled_qty)
    for h in holds:
        ref = h["ref"]
        status = h["status"]
        if h["hold_type"] == "regular" and status == "approved":
            expires_at = to_date_str(h["expires_at"])
            unexpired = (not expires_at) or (date.fromisoformat(expires_at) > TODAY)
            if unexpired:
                h_reg[ref] = h_reg.get(ref, 0) + (to_float(h["qty"]) or 0)
        elif h["hold_type"] == "strategic" and status == "approved":
            qty = to_float(h["qty"]) or 0
            fulfilled = to_float(h["fulfilled_qty"]) or 0
            h_str[ref] = h_str.get(ref, 0) + (qty - fulfilled)

    items = []
    for p in products:
        if not to_bool(p["is_active"]):
            continue
        sku = p["sku"]
        total_inventory = main_qty.get(sku, 0)
        hold_qty = h_reg.get(sku, 0) + h_str.get(sku, 0)
        available_inventory = max(total_inventory - hold_qty, 0)
        temperature = ""
        if to_bool(p["temp_critical"]):
            temperature = "Critical"
        elif to_bool(p["temp_sensitive"]):
            temperature = "Sensitive"

        items.append({
            "brand": p["manufacturer"] or None,
            "sku": sku,
            "name": p["name"] or None,
            "web_price": to_float(p["retail_price"]),
            "tl": to_float(p["true_low"]),
            "ao": to_float(p["approval_only"]),  # numeric column despite the "approval_only" name
            "sale_price": to_float(p["sale_price"]),
            "unit": p["uom"] or None,
            "temperature": temperature,
            "total_inventory": total_inventory,
            "available_inventory": available_inventory,
            "short_dated_3mo": short_dated_qty.get(sku, 0),
            "hold_qty": hold_qty,
        })

    items.sort(key=lambda x: x["sku"])
    return {"today": TODAY.isoformat(), "items": items}


# ── Holds Sheet ───────────────────────────────────────────────────────────────

def build_holds_sheet():
    products = read_csv("products.csv")
    holds = read_csv("inventory_holds.csv")
    name_by_sku = {p["sku"]: p["name"] for p in products}

    out = []
    for h in holds:
        out.append({
            "id": int(h["id"]),
            "rep": h["sales_rep"] or None,
            "facility": h["customer_name"] or None,
            "sku": h["ref"],
            "item_name": name_by_sku.get(h["ref"]) or None,
            "hold_type": h["hold_type"],
            "qty": to_float(h["qty"]) or 0,
            "days": int(h["hold_duration_days"]) if h["hold_duration_days"] else None,
            "date": to_date_str(h["created_at"]),
            "expires_at": h["expires_at"] or None,
            "status": h["status"],
            "rep_status": h["rep_status"] or None,
            "approved_price": to_float(h["approved_price"]),
            "notes": (h["reason"] or h["notes"] or None),
        })

    out.sort(key=lambda x: x["date"] or "", reverse=True)
    return {"today": TODAY.isoformat(), "holds": out}


# ── Daily Order List ──────────────────────────────────────────────────────────

def build_daily_orders():
    orders = read_csv("outbound_orders.csv")
    out = []
    for o in orders:
        out.append({
            "order_date": o["order_date"],
            "order_num": int(o["daily_order_number"]),
            "invoice_number": o["invoice_number"] or None,
            "customer_name": o["customer_name"] or None,
            "sales_rep": o["sales_rep"] or None,
            "ship_method": o["ship_method"] or None,
            "status": o["status"] or None,
            "ship_date": o["ship_date"] or None,
            "tracking_number": o["tracking_number"] or None,
            "notes": o["notes"] or None,
        })
    out.sort(key=lambda x: (x["order_date"], x["order_num"]), reverse=True)
    return {"orders": out}


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    hot_codes = build_hot_codes()
    holds_sheet = build_holds_sheet()
    daily_orders = build_daily_orders()

    for name, data in (
        ("hot_codes.json", hot_codes),
        ("holds_sheet.json", holds_sheet),
        ("daily_orders.json", daily_orders),
    ):
        path = os.path.join(OUT_DIR, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Wrote {path}")

    print(f"  hot_codes: {len(hot_codes['items'])} active products")
    print(f"  holds_sheet: {len(holds_sheet['holds'])} holds")
    print(f"  daily_orders: {len(daily_orders['orders'])} orders")


if __name__ == "__main__":
    main()
