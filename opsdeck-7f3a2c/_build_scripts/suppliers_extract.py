"""
Extracts suppliers + contacts + communications + documents into a single
Clone/data/suppliers/suppliers.json used by both suppliers/list.html and
suppliers/detail.html.

Mirrors the SQL/logic in surgicentral/suppliers/routes.py:
  - list_suppliers(): stats (total/preferred/expiring/unvetted active suppliers),
    left join primary contact, last comm date, ordered by preferred_vendor desc, name.
  - detail(): contacts ordered is_primary desc, name; comms ordered comm_date desc,
    created_at desc; docs ordered created_at desc.

Snapshot date (frozen "today" for date-math, since this is a static site with
no live clock-dependent backend): 2026-07-23, matching the CSV dump date.

Source CSVs (read-only, never copied into Clone/):
  suppliers.csv, supplier_contacts.csv, supplier_communications.csv,
  supplier_documents.csv
"""
import csv
import json
import os
from datetime import date

RAW_DIR = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT_DIR = r"C:\users\gary\surgi_central\Clone\data\suppliers"

TODAY = date(2026, 7, 23)


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def to_bool(v):
    return str(v).strip().lower() in ("t", "true", "1", "yes")


def to_int(v):
    v = (v or "").strip()
    return int(v) if v else None


def to_date_str(v):
    v = (v or "").strip()
    return v or None  # already YYYY-MM-DD from Postgres dump, or empty


def main():
    suppliers_rows = read_csv("suppliers.csv")
    contacts_rows = read_csv("supplier_contacts.csv")
    comms_rows = read_csv("supplier_communications.csv")
    docs_rows = read_csv("supplier_documents.csv")

    contacts_by_supplier = {}
    for c in contacts_rows:
        contacts_by_supplier.setdefault(int(c["supplier_id"]), []).append(c)
    comms_by_supplier = {}
    for c in comms_rows:
        comms_by_supplier.setdefault(int(c["supplier_id"]), []).append(c)
    docs_by_supplier = {}
    for d in docs_rows:
        docs_by_supplier.setdefault(int(d["supplier_id"]), []).append(d)

    suppliers = []
    for s in suppliers_rows:
        sid = int(s["id"])
        is_active = to_bool(s["is_active"])

        contacts = contacts_by_supplier.get(sid, [])
        # is_primary DESC, name ASC
        contacts_sorted = sorted(
            contacts,
            key=lambda c: (not to_bool(c["is_primary"]), c["name"].lower()),
        )
        contacts_out = [
            {
                "id": int(c["id"]),
                "name": c["name"],
                "title": c["title"] or None,
                "email": c["email"] or None,
                "phone": c["phone"] or None,
                "is_primary": to_bool(c["is_primary"]),
            }
            for c in contacts_sorted
        ]
        primary = next((c for c in contacts_out if c["is_primary"]), None)
        if not primary and contacts_out:
            primary = None  # no primary flagged -> matches LEFT JOIN ... AND is_primary=true (NULL)

        comms = comms_by_supplier.get(sid, [])
        comms_sorted = sorted(
            comms, key=lambda c: (c["comm_date"], c["created_at"]), reverse=True
        )
        comms_out = [
            {
                "id": int(c["id"]),
                "comm_date": c["comm_date"],
                "comm_type": c["comm_type"],
                "logged_by_name": c["logged_by_name"] or None,
                "summary": c["summary"] or None,
                "body": c["body"] or None,
            }
            for c in comms_sorted
        ]
        last_comm_date = comms_sorted[0]["comm_date"] if comms_sorted else None

        docs = docs_by_supplier.get(sid, [])
        docs_sorted = sorted(docs, key=lambda d: d["created_at"], reverse=True)
        docs_out = [
            {
                "id": int(d["id"]),
                "display_label": d["display_label"],
                "original_filename": d["original_filename"],
                "file_size": to_int(d["file_size"]),
                "uploaded_by_name": d["uploaded_by_name"] or None,
                "notes": d["notes"] or None,
                "created_at": d["created_at"],
            }
            for d in docs_sorted
        ]

        suppliers.append(
            {
                "id": sid,
                "name": s["name"],
                "address_line1": s["address_line1"] or None,
                "address_line2": s["address_line2"] or None,
                "city": s["city"] or None,
                "state": s["state"] or None,
                "zip_code": s["zip_code"] or None,
                "website": s["website"] or None,
                "notes": s["notes"] or None,
                "tags": s["tags"] or None,
                "date_vetted": to_date_str(s["date_vetted"]),
                "preferred_vendor": to_bool(s["preferred_vendor"]),
                "contract_expires_on": to_date_str(s["contract_expires_on"]),
                "payment_terms": s["payment_terms"] or None,
                "lead_time_days": to_int(s["lead_time_days"]),
                "is_active": is_active,
                "primary_contact_name": primary["name"] if primary else None,
                "primary_contact_email": primary["email"] if primary else None,
                "primary_contact_phone": primary["phone"] if primary else None,
                "last_comm_date": last_comm_date,
                "contacts": contacts_out,
                "comms": comms_out,
                "docs": docs_out,
            }
        )

    # Order: preferred_vendor DESC, name ASC (active suppliers first page shows active only by default)
    suppliers.sort(key=lambda s: (not s["preferred_vendor"], s["name"].lower()))

    active = [s for s in suppliers if s["is_active"]]
    total = len(active)
    preferred = sum(1 for s in active if s["preferred_vendor"])
    expiring = 0
    unvetted = 0
    for s in active:
        if s["contract_expires_on"]:
            exp = date.fromisoformat(s["contract_expires_on"])
            days_left = (exp - TODAY).days
            if 0 <= days_left <= 90:
                expiring += 1
        if not s["date_vetted"]:
            unvetted += 1

    out = {
        "today": TODAY.isoformat(),
        "stats": {
            "total": total,
            "preferred": preferred,
            "expiring": expiring,
            "unvetted": unvetted,
        },
        "comm_types": ["Meeting", "Phone", "Sent Email", "Received Email", "Other"],
        "suppliers": suppliers,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "suppliers.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print(f"Wrote {out_path}")
    print(f"  suppliers: {len(suppliers)} (active={total}, preferred={preferred}, "
          f"expiring<=90d={expiring}, unvetted={unvetted})")
    print(f"  contacts total: {len(contacts_rows)}, comms total: {len(comms_rows)}, "
          f"docs total: {len(docs_rows)}")


if __name__ == "__main__":
    main()
