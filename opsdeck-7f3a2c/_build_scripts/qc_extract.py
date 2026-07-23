"""
Extraction script for the QC module — reproduces the logic in
../../surgicentral/qc/routes.py against the raw CSV snapshot in
../../_raw_db_backup_2026-07-23/.

The real qc/index and qc/batch pages are scoped by (date, checker, PO),
derived from inbound_scans rows whose `ptracking` matches the
'<vendor> <po_number>' pattern. Rather than embedding all ~192k
inbound_scans rows, this script scans the CSV once and keeps only rows
for the 3 dates where that pattern actually produced QC activity in this
snapshot (2026-05-19, 2026-05-20, 2026-06-22 — the only dates for which
qc_batches rows exist), which is a tiny slice (~20 rows).

Run: python qc_extract.py   (from Clone/_build_scripts/)

Outputs:
    Clone/data/qc/index.json      — date -> checkers -> POs
    Clone/data/qc/batch.json      — (date, checker, po) -> line items + batch state
    Clone/data/qc/lead.json       — per-PO rollup across checkers
    Clone/data/qc/lead_review.json — per-PO merged line items for lead review
    Clone/data/qc/locations.json  — full warehouse_locations table (4,926 rows)
    Clone/data/qc/notes.json      — full qc_note_templates table (356 rows)
"""
import csv
import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

RAW = os.path.join(os.path.dirname(__file__), '..', '..', '_raw_db_backup_2026-07-23')
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'qc')
os.makedirs(OUT, exist_ok=True)

ET = ZoneInfo('America/New_York')
TODAY = datetime.strptime('2026-07-23', '%Y-%m-%d').date()

QC_DATES = ['2026-05-19', '2026-05-20', '2026-06-22']

REJECTION_REASONS = [
    'Rejected: <3mo Dating',
    'Rejected: Blister Damage (Cracked, Dented)',
    'Rejected: Water Issue',
    'Rejected: Broken Seal',
    'Rejected: Expired',
    'Rejected: Foreign Debris',
    'Rejected: Foreign Label',
    'Rejected: Kit (missing or non-verifiable components)',
    'Rejected: Multiple Issues, Please Inquire',
    'Rejected: Other',
    'Rejected: Patient Label Issue',
    'Rejected: Product Damaged',
    'Rejected: Product Missing',
    'Rejected: Recalled',
    'Rejected: Residue/Markings on Primary Packaging',
    'Rejected: Stains or Bio-Hazard',
    'Rejected: Sterility Breach',
    'Rejected: Temperature Tag Exposure',
    'Rejected: Primary Label Damage',
    'Rejected: Box Damaged',
]


def _parse_utc(s):
    if not s:
        return None
    s = s.strip()
    s = re.sub(r'\+00$', '+00:00', s)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _et_date(s):
    dt = _parse_utc(s)
    return dt.astimezone(ET).date().isoformat() if dt else None


def _parse_po(ptracking):
    """Port of qc/routes.py _parse_po: '(everything) (last token)'."""
    if not ptracking:
        return None, None
    m = re.search(r'(.+)\s+(\S+)\s*$', ptracking.strip())
    if m:
        return m.group(1).strip(), m.group(2)
    return None, None


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ── Load small supporting tables in full ────────────────────────────────────

def load_products():
    products = {}
    with open(os.path.join(RAW, 'products.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            products[row['sku']] = row
    return products


def load_sku_map():
    m = {}
    with open(os.path.join(RAW, 'sku_map.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            m[row['our_sku']] = row
    return m


def load_inventory(products):
    """current_inventory approximated as surgi_qty + wholesale_qty
    (the live schema exposes a computed `total_qty`; this CSV snapshot
    only carries the two raw balances that feed it)."""
    by_product_id = {}
    with open(os.path.join(RAW, 'inventory.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            by_product_id[row['product_id']] = _f(row['surgi_qty']) + _f(row['wholesale_qty'])
    by_sku = {}
    for sku, p in products.items():
        if p['id'] in by_product_id:
            by_sku[sku] = by_product_id[p['id']]
    return by_sku


def load_warehouse_locations():
    locs = []
    loc_map = {}
    with open(os.path.join(RAW, 'warehouse_locations.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            entry = {'id': int(row['id']), 'item_code': row['item_code'], 'location': row['location']}
            locs.append(entry)
            loc_map[row['item_code'].upper()] = row['location']
    return locs, loc_map


def load_note_templates():
    notes = []
    note_map = {}
    with open(os.path.join(RAW, 'qc_note_templates.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            entry = {
                'id': int(row['id']),
                'ref_ea': row['ref_ea'] or None,
                'ref_bx': row['ref_bx'] or None,
                'note': row['note'],
            }
            notes.append(entry)
            if row['ref_ea']:
                note_map[row['ref_ea'].upper()] = row['note']
            if row['ref_bx']:
                note_map[row['ref_bx'].upper()] = row['note']
    return notes, note_map


def load_qc_batches():
    batches = []
    with open(os.path.join(RAW, 'qc_batches.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            batches.append({
                'id': int(row['id']),
                'po_number': row['po_number'],
                'supplier': row['supplier'] or None,
                'status': row['status'],
                'started_at': row['started_at'],
                'started_et_date': _et_date(row['started_at']),
                'submitted_at': row['submitted_at'] or None,
                'checker_name': row['checker_name'],
                'finalized_at': row['finalized_at'] or None,
            })
    return batches


def load_qc_line_items():
    items_by_batch = {}
    with open(os.path.join(RAW, 'qc_line_items.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            bid = int(row['qc_batch_id'])
            items_by_batch.setdefault(bid, []).append({
                'id': int(row['id']),
                'ref': row['ref'],
                'lot': row['lot'] or None,
                'exp_date': row['exp_date'] or None,
                'accepted_qty': _f(row['accepted_qty']),
                'rejected_qty': _f(row['rejected_qty']),
                'damaged_qty': _f(row['damaged_qty']),
                'rejection_reason': row['rejection_reason'] or None,
                'notes': row['notes'] or None,
                'box_verified': row['box_verified'] == 't',
                'scanned_qty': _f(row['scanned_qty']),
                'short_dated_lt3mo': row['short_dated_lt3mo'] == 't',
                'short_dated_3to18mo': row['short_dated_3to18mo'] == 't',
            })
    return items_by_batch


def load_po_ordered_qtys(products):
    """po_number -> {sku: qty_ordered} via purchase_orders + po_lines + products."""
    po_num_by_id = {}
    with open(os.path.join(RAW, 'purchase_orders.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['po_number'] in ('14080', '14081', '14094', '14113'):
                po_num_by_id[row['id']] = row['po_number']

    sku_by_product_id = {p['id']: sku for sku, p in products.items()}

    result = {}
    with open(os.path.join(RAW, 'po_lines.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['po_id'] not in po_num_by_id:
                continue
            po_num = po_num_by_id[row['po_id']]
            sku = sku_by_product_id.get(row['product_id'])
            if not sku:
                continue
            result.setdefault(po_num, {})[sku.upper()] = result.setdefault(po_num, {}).get(sku.upper(), 0) + _f(row['qty_ordered'])
    return result


# ── Inbound scans scoped to the 3 QC-relevant dates ─────────────────────────

def load_qc_scans():
    """All inbound_scans rows on QC_DATES with ptracking containing a space
    (mirrors the 'ptracking LIKE %% %%' filter in qc.qc_index/qc_batch)."""
    rows = []
    with open(os.path.join(RAW, 'inbound_scans.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            et_date = _et_date(row['scan_date'])
            if et_date not in QC_DATES:
                continue
            ptracking = row['ptracking'] or ''
            if ' ' not in ptracking:
                continue
            rows.append({**row, '_et_date': et_date})
    return rows


def main():
    products      = load_products()
    sku_map       = load_sku_map()
    inventory     = load_inventory(products)
    locations, loc_map = load_warehouse_locations()
    note_templates, note_map = load_note_templates()
    qc_batches    = load_qc_batches()
    line_items_by_batch = load_qc_line_items()
    ordered_qtys  = load_po_ordered_qtys(products)
    scans         = load_qc_scans()

    # batch lookup: (po_number, checker_name, started_et_date) -> batch
    batch_lookup = {}
    for b in qc_batches:
        batch_lookup[(b['po_number'], b['checker_name'], b['started_et_date'])] = b

    # ── qc/index.json: date -> checkers -> pos ──────────────────────────
    index_data = {}
    for d in QC_DATES:
        day_rows = [r for r in scans if r['_et_date'] == d]
        checkers = sorted({r['scanned_by'] for r in day_rows if r['scanned_by']})
        checker_pos = {}
        for checker in checkers:
            po_map = {}
            for r in day_rows:
                if r['scanned_by'] != checker:
                    continue
                vendor, po_num = _parse_po(r['ptracking'])
                if po_num and po_num not in po_map:
                    po_map[po_num] = vendor or ''
            checker_pos[checker] = sorted(po_map.items())
        index_data[d] = {'checkers': checkers, 'pos_by_checker': checker_pos}

    # ── qc/batch.json: (date|checker|po) -> items + batch state ─────────
    batch_data = {}
    for d in QC_DATES:
        day_rows = [r for r in scans if r['_et_date'] == d]
        for checker, pos in index_data[d]['pos_by_checker'].items():
            for po_num, _vendor in pos:
                supplier = ''
                agg = {}
                for r in day_rows:
                    if r['scanned_by'] != checker:
                        continue
                    vendor, parsed_po = _parse_po(r['ptracking'])
                    if parsed_po != po_num:
                        continue
                    if vendor and not supplier:
                        supplier = vendor
                    key = (r['ref'], r['lot'] or '', r['exp_date'] or '')
                    if key not in agg:
                        prod = products.get(r['ref'], {})
                        sm = sku_map.get(r['ref'], {})
                        agg[key] = {
                            'ref': r['ref'],
                            'gtin': r['gtin'] or None,
                            'lot': r['lot'] or None,
                            'exp_date': r['exp_date'] or None,
                            'scanned_qty': 0.0,
                            'brand': prod.get('manufacturer') or '',
                            'item_name': prod.get('name') or '',
                            'unit_type': sm.get('unit_type') or '',
                            'units_per_pkg': _f(sm.get('units_per_pkg'), None) if sm.get('units_per_pkg') else None,
                            'current_inventory': inventory.get(r['ref'], 0.0),
                        }
                    agg[key]['scanned_qty'] += _f(r['qty'])
                items = list(agg.values())

                today = TODAY
                po_ordered = ordered_qtys.get(po_num, {})
                for item in items:
                    exp = item['exp_date']
                    days = (datetime.strptime(exp, '%Y-%m-%d').date() - today).days if exp else None
                    item['sd_lt3mo'] = bool(days is not None and 0 <= days <= 90)
                    item['sd_3to18mo'] = bool(days is not None and 91 <= days <= 547)

                    sku = item['ref'] or ''
                    item['is_box'] = sku.upper().endswith('B') and item['unit_type'] in ('box', 'B')
                    item['box_label'] = (f"Box of {int(item['units_per_pkg'])}"
                                         if item['is_box'] and item['units_per_pkg'] else '')

                    ordered = po_ordered.get(sku.upper())
                    item['ordered_qty'] = ordered
                    item['qty_mismatch'] = (round(item['scanned_qty'] - ordered, 2)
                                             if ordered is not None else None)

                    # No recall matches found for any of these SKUs' base refs
                    # in recall_inventory_matches.csv as of this snapshot.
                    item['recalled'] = False
                    item['recall_number'] = None
                    item['recall_reason'] = None
                    item['recall_link'] = None

                batch = batch_lookup.get((po_num, checker, d))
                batch_id = batch['id'] if batch else None
                batch_status = batch['status'] if batch else None

                saved = {}
                if batch_id:
                    for li in line_items_by_batch.get(batch_id, []):
                        key = (li['ref'], li['lot'] or '', li['exp_date'] or '')
                        saved[key] = li

                for item in items:
                    k = (item['ref'], item['lot'] or '', item['exp_date'] or '')
                    sv = saved.get(k, {})
                    item['accepted_qty'] = sv.get('accepted_qty', '')
                    item['rejected_qty'] = sv.get('rejected_qty', '')
                    item['damaged_qty'] = sv.get('damaged_qty', '')
                    item['rejection_reason'] = sv.get('rejection_reason', '')
                    item['box_verified'] = sv.get('box_verified', False)
                    saved_note = sv.get('notes', '')
                    template_note = note_map.get((item['ref'] or '').upper(), '')
                    item['notes'] = saved_note if saved_note else template_note
                    item['note_from_template'] = bool(not saved_note and template_note)
                    item['wh_location'] = loc_map.get((item['ref'] or '').upper(), '')

                batch_key = f"{d}|{checker}|{po_num}"
                batch_data[batch_key] = {
                    'selected_date': d, 'checker_name': checker, 'po_num': po_num,
                    'supplier': supplier, 'items': items,
                    'batch_id': batch_id, 'batch_status': batch_status,
                }

    # ── qc/lead.json: per-PO rollup per date ────────────────────────────
    lead_data = {}
    incoming_box_map = {}
    with open(os.path.join(RAW, 'incoming_shipments.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            if row['po_number'] and row['total_boxes']:
                incoming_box_map.setdefault(row['po_number'], int(row['total_boxes']))

    for d in QC_DATES:
        day_batches = [b for b in qc_batches if b['started_et_date'] == d]
        by_po = {}
        for b in day_batches:
            po = by_po.setdefault(b['po_number'], {
                'po_number': b['po_number'], 'supplier': b['supplier'],
                'batch_count': 0, 'submitted_count': 0, 'finalized_count': 0,
                'checkers': set(), 'total_accepted': 0.0, 'total_rejected': 0.0,
                'total_scanned': 0.0, 'total_sd_lt3mo': 0.0, 'total_sd_3to18mo': 0.0,
            })
            po['batch_count'] += 1
            if b['status'] in ('submitted', 'finalized'):
                po['submitted_count'] += 1
            if b['status'] == 'finalized':
                po['finalized_count'] += 1
            po['checkers'].add(b['checker_name'])
            for li in line_items_by_batch.get(b['id'], []):
                po['total_accepted'] += li['accepted_qty']
                po['total_rejected'] += li['rejected_qty']
                po['total_scanned'] += li['scanned_qty']
                if li['short_dated_lt3mo']:
                    po['total_sd_lt3mo'] += li['scanned_qty']
                if li['short_dated_3to18mo']:
                    po['total_sd_3to18mo'] += li['scanned_qty']

        pos_list = []
        for po in by_po.values():
            po['checkers'] = ', '.join(sorted(po['checkers']))
            po['total_boxes'] = incoming_box_map.get(po['po_number'])
            if po['finalized_count'] == po['batch_count']:
                po['lead_status'] = 'finalized'
            elif po['submitted_count'] == po['batch_count']:
                po['lead_status'] = 'ready'
            else:
                po['lead_status'] = 'in_progress'
            pos_list.append(po)
        lead_data[d] = sorted(pos_list, key=lambda p: p['po_number'])

    # ── qc/lead_review.json: (date|po) -> merged items across checkers ──
    lead_review_data = {}
    for d, pos_list in lead_data.items():
        for po in pos_list:
            po_num = po['po_number']
            day_batches = [b for b in qc_batches
                           if b['started_et_date'] == d and b['po_number'] == po_num]
            all_submitted = all(b['status'] in ('submitted', 'finalized') for b in day_batches)
            is_finalized = all(b['status'] == 'finalized' for b in day_batches)
            supplier = day_batches[0]['supplier'] if day_batches else ''

            merged = {}
            for b in day_batches:
                for li in line_items_by_batch.get(b['id'], []):
                    prod = products.get(li['ref'], {})
                    key = (li['ref'], li['lot'] or '', li['exp_date'] or '')
                    if key not in merged:
                        merged[key] = {
                            'ref': li['ref'], 'lot': li['lot'], 'exp_date': li['exp_date'],
                            'short_dated_lt3mo': li['short_dated_lt3mo'],
                            'short_dated_3to18mo': li['short_dated_3to18mo'],
                            'brand': prod.get('manufacturer') or '',
                            'scanned_qty': 0.0, 'accepted_qty': 0.0,
                            'rejected_qty': 0.0, 'damaged_qty': 0.0,
                            'rejection_reason': None, 'notes': [],
                            'box_verified': False, 'checkers': [],
                        }
                    m = merged[key]
                    m['scanned_qty'] += li['scanned_qty']
                    m['accepted_qty'] += li['accepted_qty']
                    m['rejected_qty'] += li['rejected_qty']
                    m['damaged_qty'] += li['damaged_qty']
                    m['box_verified'] = m['box_verified'] or li['box_verified']
                    if li['rejection_reason'] and not m['rejection_reason']:
                        m['rejection_reason'] = li['rejection_reason']
                    if li['notes']:
                        m['notes'].append(li['notes'])
                    m['checkers'].append(b['checker_name'])

            items = []
            for m in merged.values():
                m['checkers_str'] = ', '.join(sorted(set(m['checkers'])))
                m['notes'] = ' | '.join(dict.fromkeys(m['notes']))
                m['wh_location'] = loc_map.get((m['ref'] or '').upper(), '')
                exp = m['exp_date']
                if exp:
                    days = (datetime.strptime(exp, '%Y-%m-%d').date() - TODAY).days
                    m['sd_lt3mo'] = 0 <= days <= 90
                    m['sd_3to18mo'] = 91 <= days <= 547
                else:
                    m['sd_lt3mo'] = False
                    m['sd_3to18mo'] = False
                del m['checkers']
                items.append(m)

            lead_review_data[f"{d}|{po_num}"] = {
                'selected_date': d, 'po_num': po_num, 'supplier': supplier,
                'batches': [{'id': b['id'], 'checker_name': b['checker_name'],
                             'status': b['status'], 'submitted_at': b['submitted_at']}
                            for b in day_batches],
                'items': items,
                'all_submitted': all_submitted, 'is_finalized': is_finalized,
            }

    # ── Write outputs ────────────────────────────────────────────────────
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'dates': index_data, 'available_dates': QC_DATES}, f, indent=0)
    with open(os.path.join(OUT, 'batch.json'), 'w', encoding='utf-8') as f:
        json.dump({'batches': batch_data, 'rejection_reasons': REJECTION_REASONS}, f, indent=0)
    with open(os.path.join(OUT, 'lead.json'), 'w', encoding='utf-8') as f:
        json.dump({'dates': lead_data, 'available_dates': QC_DATES}, f, indent=0)
    with open(os.path.join(OUT, 'lead_review.json'), 'w', encoding='utf-8') as f:
        json.dump(lead_review_data, f, indent=0)
    with open(os.path.join(OUT, 'locations.json'), 'w', encoding='utf-8') as f:
        json.dump({'locations': locations}, f, indent=0)
    with open(os.path.join(OUT, 'notes.json'), 'w', encoding='utf-8') as f:
        json.dump({'notes': note_templates}, f, indent=0)

    print(f"index.json: {len(QC_DATES)} dates")
    print(f"batch.json: {len(batch_data)} (date|checker|po) batches")
    print(f"lead.json: {sum(len(v) for v in lead_data.values())} PO rollups")
    print(f"lead_review.json: {len(lead_review_data)} PO reviews")
    print(f"locations.json: {len(locations)} rows")
    print(f"notes.json: {len(note_templates)} rows")


if __name__ == '__main__':
    main()
