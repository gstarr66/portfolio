"""
Extracts data for the New Items module.

Mirrors surgicentral/new_items/routes.py.

new_item_requests.csv has 0 rows in this snapshot (real: the workflow exists
but nothing was in-flight in Postgres at dump time). So the dashboard is a
genuine empty state ("No new item requests.") with all counts at 0 - not a
bug, not padded with fabricated rows.

CATEGORIES and TAX_CLASSES are static business-logic constants hardcoded in
routes.py (not DB rows / not sensitive), reproduced here so the create/complete
forms render the same dropdowns as the live app.
"""
import csv
import json
import os

RAW_DIR = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT_DIR = r"C:\users\gary\surgi_central\Clone\data\new_items"

CATEGORIES = [
    ["ENT", "E"],
    ["ENTVascular", "EV"],
    ["Endomechanical", "Y"],
    ["GYN/Urology", "G"],
    ["GYN/UrologyEndomechanical", "GY"],
    ["GYN/UrologyMesh", "MG"],
    ["Hemostat / Wound Care", "H"],
    ["Hemostat / Wound CareOrthopedicSpine / Neurology", "SOH"],
    ["Hemostat / Wound CareSpine / Neurology", "HS"],
    ["Mesh", "M"],
    ["MeshEndomechanical", "YM"],
    ["Orthopedic", "O"],
    ["OrthopedicSpine / Neurology", "SO"],
    ["OrthopedicSpine / NeurologyEndomechanical", "YOS"],
    ["Robotics", "R"],
    ["Specialty", "Z"],
    ["Spine / Neurology", "S"],
    ["Vascular", "V"],
]

TAX_CLASSES = ["P0000000", "PH404914"]


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main():
    rows = read_csv("new_item_requests.csv")  # expected: []

    requests_out = []
    for r in rows:
        requests_out.append(
            {
                "id": int(r["id"]),
                "gtin": r["gtin"] or None,
                "brand": r["brand"] or None,
                "item_number": r["item_number"] or None,
                "sku": r["sku"] or None,
                "unit": r["unit"] or None,
                "status": r["status"] or None,
                "inbound_by": r["inbound_by"] or None,
                "inbound_at": r["inbound_at"] or None,
                "ic_by": r["ic_by"] or None,
                "ic_at": r["ic_at"] or None,
                "lots_created": int(r["lots_created"]) if r["lots_created"] else 0,
                "qty_imported": float(r["qty_imported"]) if r["qty_imported"] else 0.0,
                "created_at": r["created_at"] or None,
            }
        )

    status_order = {
        "inbound_pending": 1,
        "inventory_control_pending": 2,
        "submitted": 3,
        "override_submitted": 4,
    }
    requests_out.sort(key=lambda r: (status_order.get(r["status"], 99), r["created_at"] or ""), reverse=False)

    counts = {
        "inbound_pending": sum(1 for r in requests_out if r["status"] == "inbound_pending"),
        "inventory_control_pending": sum(1 for r in requests_out if r["status"] == "inventory_control_pending"),
        "submitted": sum(1 for r in requests_out if r["status"] in ("submitted", "override_submitted")),
    }

    out = {
        "requests": requests_out,
        "counts": counts,
        "categories": CATEGORIES,
        "tax_classes": TAX_CLASSES,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "new_items.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {out_path}")
    print(f"  requests: {len(requests_out)} (source CSV rows: {len(rows)}) counts={counts}")


if __name__ == "__main__":
    main()
