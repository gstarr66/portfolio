"""
Extraction script for the Warehouse module (inbound/outbound scan logs +
native inbound scanning sessions) — reproduces the logic in
../../surgicentral/warehouse/routes.py against the raw CSV snapshot in
../../_raw_db_backup_2026-07-23/, and writes small JSON files for the
static clone.

Run: python warehouse_extract.py   (from Clone/_build_scripts/)

Outputs:
    Clone/data/warehouse/inbound.json    — inbound scan log, 5 sample dates
    Clone/data/warehouse/outbound.json   — outbound scan log, 5 sample dates
    Clone/data/warehouse/scan_sessions.json — the 6 real inbound_scan_sessions
        rows + their scans, plus a small canned-barcode list used to
        simulate scanning in scan_live.html (fake-live demoStore flow)

Notes on scope (see _BUILD_CONVENTIONS.md — inbound_scans/outbound_scans are
~193k/~206k rows, must not be embedded in full):
    - inbound.json ships only 5 representative recent dates
      (2026-07-16, 07-17, 07-20, 07-21, 07-22 — the 5 most recent dates
      in the snapshot with a meaningful row count).
    - outbound.json ships 5 representative dates near the end of the
      outbound_scans history (2026-05-14, 05-15, 05-18, 05-19, 06-24 —
      native outbound scanning was never built per project notes, so real
      outbound_scans data trails off in mid-2026; 06-24 is the literal
      most recent row in the table, just 6 records).
"""
import csv
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

RAW = os.path.join(os.path.dirname(__file__), '..', '..', '_raw_db_backup_2026-07-23')
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'warehouse')
os.makedirs(OUT, exist_ok=True)

ET = ZoneInfo('America/New_York')

INBOUND_DATES  = ['2026-07-16', '2026-07-17', '2026-07-20', '2026-07-21', '2026-07-22']
OUTBOUND_DATES = ['2026-05-14', '2026-05-15', '2026-05-18', '2026-05-19', '2026-06-24']


def _parse_utc(s):
    if not s:
        return None
    s = s.strip()
    # e.g. "2026-06-22 15:28:54.785494+00" or "...+00:00"
    s = re.sub(r'\+00$', '+00:00', s)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _et_date_and_time(scan_date_str):
    dt = _parse_utc(scan_date_str)
    if not dt:
        return None, None
    dt_et = dt.astimezone(ET)
    return dt_et.date().isoformat(), dt_et.strftime('%H:%M:%S')


def _parse_ptracking(ptracking):
    """Port of warehouse/routes.py _parse_ptracking: '(vendor) (po_num)' from
    trailing '<word> <4-6 digit number>' pattern."""
    if not ptracking:
        return None, None
    m = re.search(r'(\S+)\s+(\d{4,6})\s*$', ptracking.strip())
    if m:
        return m.group(1), m.group(2)
    return None, None


# ── Inbound log ────────────────────────────────────────────────────────────

def extract_inbound_log():
    by_date = {d: [] for d in INBOUND_DATES}
    with open(os.path.join(RAW, 'inbound_scans.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            et_date, et_time = _et_date_and_time(row['scan_date'])
            if et_date not in by_date:
                continue
            ptracking = row['ptracking'] or None
            # Real SQL: WHERE (ptracking IS NULL OR ptracking LIKE '% %')
            if ptracking and ' ' not in ptracking:
                continue
            vendor, po_num = _parse_ptracking(ptracking)
            by_date[et_date].append({
                'id': row['id'],
                'time': et_time,
                'ref': row['ref'] or None,
                'lot': row['lot'] or None,
                'exp_date': row['exp_date'] or None,
                'qty': float(row['qty']) if row['qty'] else None,
                'vendor': vendor,
                'po_num': po_num,
                'ptracking': ptracking,
                'scanned_by': row['scanned_by'] or None,
                'source': row['source'] or None,
            })

    dates_out = {}
    for d, scans in by_date.items():
        scans.sort(key=lambda s: s['time'] or '', reverse=True)
        total_qty = sum(s['qty'] or 0 for s in scans)
        dates_out[d] = {'scans': scans, 'total_qty': round(total_qty, 2)}

    return {
        'note': ("Showing 5 representative dates from the 2026-07-23 snapshot "
                 "(inbound_scans has ~192,720 rows total across 1,264 distinct "
                 "days) — a live server would answer any date on demand."),
        'available_dates': INBOUND_DATES,
        'default_date': '2026-07-22',
        'dates': dates_out,
    }


# ── Outbound log ───────────────────────────────────────────────────────────

def extract_outbound_log():
    by_date = {d: [] for d in OUTBOUND_DATES}
    with open(os.path.join(RAW, 'outbound_scans.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            et_date, et_time = _et_date_and_time(row['scan_date'])
            if et_date not in by_date:
                continue
            by_date[et_date].append({
                'id': row['id'],
                'time': et_time,
                'ref': row['ref'] or None,
                'lot': row['lot'] or None,
                'exp_date': row['exp_date'] or None,
                'qty': float(row['qty']) if row['qty'] else None,
                'invoice': row['invoice'] or None,
                'scanned_by': row['scanned_by'] or None,
                'source': row['source'] or None,
            })

    dates_out = {}
    for d, scans in by_date.items():
        scans.sort(key=lambda s: s['time'] or '', reverse=True)
        total_qty = sum(s['qty'] or 0 for s in scans)
        dates_out[d] = {'scans': scans, 'total_qty': round(total_qty, 2)}

    return {
        'note': ("Showing 5 representative dates from the 2026-07-23 snapshot "
                 "(outbound_scans has ~205,556 rows total). Native outbound "
                 "scanning hadn't shipped yet as of this snapshot (per project "
                 "notes), so the table's most recent rows trail off mid-2026 — "
                 "2026-06-24 (6 rows) is the literal last date in the table."),
        'available_dates': OUTBOUND_DATES,
        'default_date': '2026-05-18',
        'dates': dates_out,
    }


# ── Native inbound scanning sessions ────────────────────────────────────────

def _exp_status(exp_date_str, today_str='2026-07-23'):
    if not exp_date_str:
        return 'ok'
    exp = datetime.strptime(exp_date_str[:10], '%Y-%m-%d').date()
    today = datetime.strptime(today_str, '%Y-%m-%d').date()
    days = (exp - today).days
    if days < 0:
        return 'expired'
    if days <= 90:
        return 'short_dated'
    return 'ok'


def extract_scan_sessions():
    sessions = []
    with open(os.path.join(RAW, 'inbound_scan_sessions.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sessions.append({
                'id': int(row['id']),
                'po_number': row['po_number'],
                'supplier': row['supplier'] or None,
                'scanned_by': row['scanned_by'] or None,
                'box_current': int(row['box_current']) if row['box_current'] else None,
                'box_total': int(row['box_total']) if row['box_total'] else None,
                'scan_date': row['scan_date'],
                'status': row['status'],
                'physical_count_verified': row['physical_count_verified'] == 't',
            })

    # products keyed by sku for the small set referenced by these sessions
    refs = {'23-112-1E', '5500-25S-301E', 'EMP-FBX200HSE'}
    products = {}
    with open(os.path.join(RAW, 'products.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['sku'] in refs:
                products[row['sku']] = {
                    'sku': row['sku'],
                    'item_number': row['item_number'] or None,
                    'name': row['name'] or None,
                    'gtin': row['gtin'] or None,
                }

    scans_by_session = {}
    with open(os.path.join(RAW, 'inbound_scans.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sid = row['session_id']
            if not sid:
                continue
            sku = row['ref'] or None
            u = (sku or '').upper()
            unit_type = 'B' if u.endswith('B') else ('E' if u.endswith('E') else '')
            prod = products.get(sku, {})
            scans_by_session.setdefault(sid, []).append({
                'id': int(row['id']),
                'gtin': row['gtin'] or None,
                'sku': sku,
                'item_number': prod.get('item_number'),
                'name': prod.get('name'),
                'lot': row['lot'] or None,
                'exp_date': row['exp_date'] or None,
                'exp_status': _exp_status(row['exp_date']),
                'zone': row['zone'] or 'main',
                'unit_type': unit_type,
                'is_new': sku not in products,
            })

    # Canned GS1 barcodes for the "Simulate Scan" demo button — built from the
    # same real GTIN/lot/exp combinations already used in sessions 1/3/5, so a
    # simulated scan resolves against the same known product/lot data as the
    # real historical sessions (bracket-format GS1, AI 01=GTIN 17=exp 10=lot).
    canned_barcodes = [
        '(01)00763000738501(17)300324(10)AQ25032050',   # 23-112-1E
        '(01)07613327422474(17)260401(10)24089037',     # 5500-25S-301E
        '(01)08033945938413(17)260805(10)H213272',      # EMP-FBX200HSE (main lot)
    ]

    return {
        'note': ("The 6 real inbound_scan_sessions rows from the 2026-07-23 "
                 "snapshot. Sessions 1,3,5 (PO 14080) and 4 (PO 14081) carry "
                 "their real scanned lines; session 6 (PO 14080, box 2 of 2) "
                 "was left open with nothing scanned yet — starting a new "
                 "session in this demo behaves the same way, then the "
                 "'Simulate Scan' button appends real product/lot data via "
                 "demoStore, exactly like a physical barcode scanner would."),
        'sessions': sessions,
        'scans_by_session': scans_by_session,
        'products': products,
        'canned_barcodes': canned_barcodes,
    }


def main():
    inbound = extract_inbound_log()
    outbound = extract_outbound_log()
    sessions = extract_scan_sessions()

    with open(os.path.join(OUT, 'inbound.json'), 'w', encoding='utf-8') as f:
        json.dump(inbound, f, indent=0)
    with open(os.path.join(OUT, 'outbound.json'), 'w', encoding='utf-8') as f:
        json.dump(outbound, f, indent=0)
    with open(os.path.join(OUT, 'scan_sessions.json'), 'w', encoding='utf-8') as f:
        json.dump(sessions, f, indent=0)

    n_in  = sum(len(v['scans']) for v in inbound['dates'].values())
    n_out = sum(len(v['scans']) for v in outbound['dates'].values())
    print(f"inbound.json:  {n_in} scan rows across {len(INBOUND_DATES)} dates")
    print(f"outbound.json: {n_out} scan rows across {len(OUTBOUND_DATES)} dates")
    print(f"scan_sessions.json: {len(sessions['sessions'])} sessions, "
          f"{sum(len(v) for v in sessions['scans_by_session'].values())} scans")


if __name__ == '__main__':
    main()
