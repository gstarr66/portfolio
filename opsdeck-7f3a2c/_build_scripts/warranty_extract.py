"""
Extracts data for the Warranty module's two pages:
  - warranty/list.html   <- data/warranty/list.json
  - warranty/detail.html <- data/warranty/detail.json (detail.html looks up
                             ?id= client-side against the full claims list,
                             same pattern as suppliers/detail.html and
                             acquisitions/detail.html)

Mirrors surgicentral/warranty/routes.py:
  - list_claims(): summary counts (open / pending_approval / ready_to_resolve
    / closed) computed with the exact same FILTER conditions as the SQL,
    then claims ordered by created_at DESC.
  - claim_detail(): full claim row, plus can_edit/can_manage/both_ok which in
    the live app depend on the logged-in user's permissions -- in this static
    demo the user is always "logged in" with every permission (per
    _BUILD_CONVENTIONS.md), so can_edit/can_manage are always true. All
    write actions (Submit, Approve/Reject, Resolve, Cancel, and the "Save
    Claim" button on new.html) are still rendered but marked
    data-demo-inert in the HTML, since Warranty has no designated
    fake-live flow in the conventions table (only Acquisitions' "new buyback
    case" does real appends).

Real live data is exactly 1 row (per the task) -- embedded as-is, no padding.

Frozen "today": 2026-07-23, matching the CSV dump date.

Source CSV (read-only, never copied into Clone/): warranty_claims.csv
"""
import csv
import json
import os
from datetime import date

RAW_DIR = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT_DIR = r"C:\users\gary\surgi_central\Clone\data\warranty"

TODAY = date(2026, 7, 23)

STATUSES = ['Open', 'Work in Progress', 'Closed', 'Cancelled']


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def none_if_blank(v):
    v = (v or "").strip()
    return v or None


def claim_out(c):
    return {
        "id": int(c["id"]),
        "claim_number": c["claim_number"],
        "sales_invoice": none_if_blank(c["sales_invoice"]),
        "customer_name": none_if_blank(c["customer_name"]),
        "status": c["status"],
        "date_initiated": none_if_blank(c["date_initiated"]),
        "claim_type": none_if_blank(c["claim_type"]),
        "sku": none_if_blank(c["sku"]),
        "lot_number": none_if_blank(c["lot_number"]),
        "expiration_date": none_if_blank(c["expiration_date"]),
        "issue": none_if_blank(c["issue"]),
        "initiated_by_name": none_if_blank(c["initiated_by_name"]),
        "submitted_at": none_if_blank(c["submitted_at"]),
        "ops_approval": c["ops_approval"],
        "ops_approved_by": none_if_blank(c["ops_approved_by"]),
        "ops_approved_at": none_if_blank(c["ops_approved_at"]),
        "acct_approval": c["acct_approval"],
        "acct_approved_by": none_if_blank(c["acct_approved_by"]),
        "acct_approved_at": none_if_blank(c["acct_approved_at"]),
        "resolution_date": none_if_blank(c["resolution_date"]),
        "resolution_details": none_if_blank(c["resolution_details"]),
        "resolved_by_name": none_if_blank(c["resolved_by_name"]),
        "resolved_at": none_if_blank(c["resolved_at"]),
        "created_at": c["created_at"],
    }


def main():
    rows = read_csv("warranty_claims.csv")
    claims = [claim_out(c) for c in rows]
    claims.sort(key=lambda c: c["created_at"], reverse=True)

    open_count = sum(1 for c in claims if c["status"] == "Open")
    pending_approval = sum(
        1 for c in claims
        if c["submitted_at"]
        and c["status"] not in ("Closed", "Cancelled")
        and (c["ops_approval"] == "Pending" or c["acct_approval"] == "Pending")
    )
    ready_to_resolve = sum(
        1 for c in claims
        if c["ops_approval"] == "Approved"
        and c["acct_approval"] == "Approved"
        and c["status"] not in ("Closed", "Cancelled")
    )
    closed_count = sum(1 for c in claims if c["status"] == "Closed")

    list_out = {
        "counts": {
            "open_count": open_count,
            "pending_approval": pending_approval,
            "ready_to_resolve": ready_to_resolve,
            "closed_count": closed_count,
        },
        "statuses": STATUSES,
        "claims": [
            {k: c[k] for k in (
                "id", "claim_number", "sales_invoice", "customer_name", "status",
                "date_initiated", "claim_type", "sku", "initiated_by_name",
                "ops_approval", "acct_approval", "submitted_at",
            )}
            for c in claims
        ],
    }

    detail_out = {
        "today": TODAY.isoformat(),
        "claims": claims,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "list.json"), "w", encoding="utf-8") as f:
        json.dump(list_out, f, indent=2)
    with open(os.path.join(OUT_DIR, "detail.json"), "w", encoding="utf-8") as f:
        json.dump(detail_out, f, indent=2)

    print(f"Wrote {os.path.join(OUT_DIR, 'list.json')}")
    print(f"Wrote {os.path.join(OUT_DIR, 'detail.json')}")
    print(f"  claims: {len(claims)} (open={open_count}, pending_approval={pending_approval}, "
          f"ready_to_resolve={ready_to_resolve}, closed={closed_count})")


if __name__ == "__main__":
    main()
