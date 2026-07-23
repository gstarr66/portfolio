"""
Extracts FDA device recall data for the Recalls module.

Mirrors surgicentral/recalls/routes.py:
  - dashboard(): total_recalls, active_recalls (status not in terminated/completed),
    total_matches / active_matches (recall_inventory_matches join - table is empty
    in this snapshot, so both are 0), last_run (most recent recall_check_log row,
    converted UTC -> America/New_York same as the real app), matches (active
    inventory matches - empty), recent (recall_date within last 30 days of the
    snapshot date, ordered recall_date desc, limit 25).
  - all_recalls(): full recall list, ordered recall_date desc, with distinct
    lowercased statuses for the filter dropdown. fda_device_recalls.csv has
    8,004 rows (NOT ~69k - that figure came from a naive `wc -l`, which
    miscounts because several `reason`/`device_name` fields contain embedded
    newlines inside quoted CSV values; proper csv.DictReader parsing gives the
    correct 8,004). Per _BUILD_CONVENTIONS.md guidance on capping large
    embedded tables, we cap the embedded set at the 2,000 most recent records
    (recall_date desc) and say so in the JSON/UI rather than truncating
    silently.
  - recall_detail(): single record by id - looked up client-side from the
    same capped list (any id linked from dashboard "recent" or all_recalls
    is, by construction, within the most-recent-2000 slice).

Snapshot / "today" reference for the 30-day recency window: 2026-07-23
(the CSV dump date), frozen at build time since this is a static site.

Source CSVs (read-only): fda_device_recalls.csv, recall_check_log.csv,
recall_inventory_matches.csv
"""
import csv
import json
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

RAW_DIR = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT_DIR = r"C:\users\gary\surgi_central\Clone\data\recalls"

TODAY = date(2026, 7, 23)
EASTERN = ZoneInfo("America/New_York")
CAP = 2000


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def trunc(s, n):
    if not s:
        return None
    s = s.strip()
    return (s[:n] + "…") if len(s) > n else s


def main():
    recalls_rows = read_csv("fda_device_recalls.csv")
    log_rows = read_csv("recall_check_log.csv")
    matches_rows = read_csv("recall_inventory_matches.csv")  # empty, 0 rows

    total_recalls = len(recalls_rows)
    active_recalls = sum(
        1 for r in recalls_rows if (r["status"] or "").strip().lower() not in ("terminated", "completed")
    )
    total_matches = len(matches_rows)
    active_matches = 0  # join is empty regardless

    # last_run - most recent by run_at
    last_run = None
    if log_rows:
        def parse_ts(s):
            # e.g. '2026-07-07 19:08:10.687718+00'
            s = s.replace(" ", "T")
            return datetime.fromisoformat(s)

        latest = max(log_rows, key=lambda r: parse_ts(r["run_at"]))
        run_at_utc = parse_ts(latest["run_at"])
        run_at_est = run_at_utc.astimezone(EASTERN)
        last_run = {
            "run_at_est": run_at_est.strftime("%m/%d/%Y %H:%M"),
            "recalls_fetched": int(latest["recalls_fetched"] or 0),
            "matches_found": int(latest["matches_found"] or 0),
            "alerts_sent": int(latest["alerts_sent"] or 0),
        }

    # Normalize + sort all recalls by recall_date desc (nulls last - none are null here)
    def norm(r):
        return {
            "id": int(r["id"]),
            "recall_number": r["recall_number"] or None,
            "device_name": r["device_name"] or None,
            "recall_firm": r["recall_firm"] or None,
            "product_code": r["product_code"] or None,
            "cfres_id": r["cfres_id"] or None,
            "recall_date": r["recall_date"] or None,
            "reason": r["reason"] or None,
            "status": r["status"] or None,
            "code_info": r["code_info"] or None,
            "created_at": r["created_at"] or None,
        }

    normalized = [norm(r) for r in recalls_rows]
    normalized.sort(key=lambda r: r["recall_date"] or "", reverse=True)

    # distinct lowercased statuses across FULL dataset (filter dropdown is independent of cap)
    statuses = sorted({(r["status"] or "").strip().lower() for r in normalized if r["status"]})

    # recent = last 30 days relative to snapshot date, limit 25
    cutoff = (TODAY - timedelta(days=30)).isoformat()
    recent = [r for r in normalized if r["recall_date"] and r["recall_date"] >= cutoff][:25]

    # Capped slice for all_recalls embed (most recent 2000)
    capped = normalized[:CAP]

    dashboard_out = {
        "today": TODAY.isoformat(),
        "total_recalls": total_recalls,
        "active_recalls": active_recalls,
        "total_matches": total_matches,
        "active_matches": active_matches,
        "last_run": last_run,
        "matches": [],  # recall_inventory_matches table is empty in this snapshot
        "recent": recent,
    }

    all_recalls_out = {
        "total": total_recalls,
        "embedded_count": len(capped),
        "truncated": len(capped) < total_recalls,
        "truncation_note": (
            f"Showing the {len(capped):,} most recent of {total_recalls:,} recalls "
            f"(by recall date) for demo performance."
            if len(capped) < total_recalls else None
        ),
        "statuses": statuses,
        "recalls": capped,
    }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "dashboard.json"), "w", encoding="utf-8") as f:
        json.dump(dashboard_out, f, indent=2)
    with open(os.path.join(OUT_DIR, "all_recalls.json"), "w", encoding="utf-8") as f:
        json.dump(all_recalls_out, f, indent=2)

    print(f"total_recalls={total_recalls} active_recalls={active_recalls} "
          f"total_matches={total_matches} recent(30d)={len(recent)} capped={len(capped)}")
    print(f"statuses={statuses}")
    print(f"last_run={last_run}")


if __name__ == "__main__":
    main()
