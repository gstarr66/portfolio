"""
Extracts data for the Acquisitions module's three pages:
  - acquisitions/list.html   <- data/acquisitions/buybacks.json
  - acquisitions/detail.html <- data/acquisitions/buybacks.json (same file;
                                 detail.html looks up ?id= client-side, same
                                 pattern as suppliers/detail.html)
  - acquisitions/cases.html  <- data/acquisitions/cases.json

Mirrors the SQL/constants in surgicentral/acquisitions/routes.py:
  - list_buybacks(): buybacks + item_count subquery, ordered by a manual
    status-priority CASE (pending_approval, approved, offered, countered,
    accepted, denied, cancelled) then created_at DESC. Stats = count by status
    across ALL buybacks (not filtered).
  - detail(): buyback row + its buyback_items (ORDER BY line_num) + at most
    one buyback_cases row (LIMIT 1) for that buyback_id.
  - cases(): buyback_cases, ordered "SF Case Closed" last then post_date DESC,
    created_at DESC. Stats = count by status across ALL cases.
  - CASE_STATUSES / STATUS_COLORS / STATUS_LABELS copied verbatim from
    routes.py so badge colors/labels match the live app exactly.

Real live data is tiny by design (per the task): 2 buybacks, 6 buyback_items,
2 buyback_cases -- embedded in full, no cap needed. Note buyback_cases row
id=1 has a blank buyback_id (an orphan case entered manually via "Add Case
Manually" before the automatic case-creation on buyback #2's acceptance created
case id=2) -- that's real data, not a bug, and is reproduced as buyback_id=None.

Frozen "today": 2026-07-23, matching the CSV dump date (used for the
expiration-date color-coding on detail.html, same logic as
buyback_items.expiration_date - today in the Jinja template).

Source CSVs (read-only, never copied into Clone/):
  buybacks.csv, buyback_items.csv, buyback_cases.csv
"""
import csv
import json
import os
from datetime import date

RAW_DIR = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT_DIR = r"C:\users\gary\surgi_central\Clone\data\acquisitions"

TODAY = date(2026, 7, 23)

STATUS_COLORS = {
    'pending_approval': 'warning',
    'approved':         'info',
    'offered':          'primary',
    'accepted':         'success',
    'denied':           'danger',
    'countered':        'warning',
    'cancelled':        'secondary',
}

STATUS_LABELS = {
    'pending_approval': 'Pending Approval',
    'approved':         'Approved — Ready to Send',
    'offered':          'Offered',
    'accepted':         'Accepted',
    'denied':           'Denied',
    'countered':        'Countered',
    'cancelled':        'Cancelled',
}

CASE_STATUSES = [
    'Offer Sent',
    'PO Issued',
    'Shipping Label Sent',
    'In Transit',
    'Received',
    'Received - Pending Verification',
    'Payment Pending',
    'SF Case Closed',
]

STATUS_PRIORITY = {
    'pending_approval': 1,
    'approved':         2,
    'offered':          3,
    'countered':        4,
    'accepted':         5,
    'denied':           6,
    'cancelled':        7,
}


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_int(v):
    v = (v or "").strip()
    return int(v) if v else None


def to_float(v):
    v = (v or "").strip()
    return float(v) if v else None


def main():
    buybacks_rows = read_csv("buybacks.csv")
    items_rows = read_csv("buyback_items.csv")
    cases_rows = read_csv("buyback_cases.csv")

    items_by_buyback = {}
    for it in items_rows:
        items_by_buyback.setdefault(int(it["buyback_id"]), []).append(it)

    case_by_buyback = {}
    for c in cases_rows:
        if c["buyback_id"]:
            case_by_buyback[int(c["buyback_id"])] = c

    def case_out(c):
        return {
            "id": int(c["id"]),
            "buyback_id": to_int(c["buyback_id"]),
            "sf_case_number": c["sf_case_number"],
            "customer_name": c["customer_name"],
            "po_number": c["po_number"] or None,
            "case_owner": c["case_owner"] or None,
            "status": c["status"],
            "post_date": c["post_date"] or None,
            "notes": c["notes"] or None,
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
        }

    buybacks = []
    for b in buybacks_rows:
        bid = int(b["id"])
        items = sorted(items_by_buyback.get(bid, []), key=lambda x: int(x["line_num"] or 0))
        items_out = [
            {
                "id": int(it["id"]),
                "line_num": int(it["line_num"]) if it["line_num"] else None,
                "manufacturer": it["manufacturer"] or None,
                "ref_number": it["ref_number"] or None,
                "unit_of_measure": it["unit_of_measure"] or None,
                "quantity": to_int(it["quantity"]),
                "expiration_date": it["expiration_date"] or None,
                "credit_per_qty": to_float(it["credit_per_qty"]),
                "cash_per_qty": to_float(it["cash_per_qty"]),
                "dating_notes": it["dating_notes"] or None,
            }
            for it in items
        ]

        case = case_by_buyback.get(bid)

        buybacks.append({
            "id": bid,
            "facility_name": b["facility_name"],
            "contact_name": b["contact_name"] or None,
            "address_line1": b["address_line1"] or None,
            "city": b["city"] or None,
            "state": b["state"] or None,
            "zip_code": b["zip_code"] or None,
            "phone": b["phone"] or None,
            "email": b["email"] or None,
            "status": b["status"],
            "total_credit_offer": to_float(b["total_credit_offer"]),
            "total_cash_offer": to_float(b["total_cash_offer"]),
            "offer_notes": b["offer_notes"] or None,
            "approved_by_name": b["approved_by_name"] or None,
            "approved_at": b["approved_at"] or None,
            "sf_case_number": b["sf_case_number"] or None,
            "po_number": b["po_number"] or None,
            "created_by_name": b["created_by_name"] or None,
            "created_at": b["created_at"],
            "updated_at": b["updated_at"],
            "item_count": len(items_out),
            "items": items_out,
            "case": case_out(case) if case else None,
        })

    # Two stable sorts: created_at DESC first, then status-priority ASC on top
    # (Python's sort is stable, so this reproduces "ORDER BY priority, created_at DESC").
    buybacks.sort(key=lambda b: b["created_at"], reverse=True)
    buybacks.sort(key=lambda b: STATUS_PRIORITY.get(b["status"], 99))

    stats = {}
    for b in buybacks_rows:
        stats[b["status"]] = stats.get(b["status"], 0) + 1

    cases_out = [case_out(c) for c in cases_rows]
    # "SF Case Closed" last, then post_date DESC, created_at DESC (3 stable sorts, innermost first)
    cases_out.sort(key=lambda c: c["created_at"], reverse=True)
    cases_out.sort(key=lambda c: (c["post_date"] or ""), reverse=True)
    cases_out.sort(key=lambda c: 1 if c["status"] == "SF Case Closed" else 0)

    case_stats = {}
    for c in cases_rows:
        case_stats[c["status"]] = case_stats.get(c["status"], 0) + 1

    buybacks_out = {
        "today": TODAY.isoformat(),
        "stats": stats,
        "STATUS_COLORS": STATUS_COLORS,
        "STATUS_LABELS": STATUS_LABELS,
        "buybacks": buybacks,
    }

    cases_file_out = {
        "today": TODAY.isoformat(),
        "stats": case_stats,
        "CASE_STATUSES": CASE_STATUSES,
        "cases": cases_out,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "buybacks.json"), "w", encoding="utf-8") as f:
        json.dump(buybacks_out, f, indent=2)
    with open(os.path.join(OUT_DIR, "cases.json"), "w", encoding="utf-8") as f:
        json.dump(cases_file_out, f, indent=2)

    print(f"Wrote {os.path.join(OUT_DIR, 'buybacks.json')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'cases.json')}")
    print(f"  buybacks: {len(buybacks)}, items total: {len(items_rows)}, cases: {len(cases_out)}")


if __name__ == "__main__":
    main()
