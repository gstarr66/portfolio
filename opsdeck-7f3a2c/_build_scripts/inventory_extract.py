"""
Extraction script for the Inventory module (static demo).

Reads the raw Postgres CSV dump (../../_raw_db_backup_2026-07-23/*.csv) and
reproduces the exact logic of surgicentral/inventory/routes.py using the
stdlib csv/json modules, then writes static JSON for Clone/inventory/*.html
to fetch.

Outputs (Clone/data/inventory/):
  summary.json              -- summary() : one row per SKU with lots
  lot_detail.json            -- lot_detail(<ref>), keyed by ref
  holds.json                 -- holds() : all hold requests (baseline;
                                 the live page layers demoStore submissions
                                 on top client-side)
  zone_moves.json             -- zone_moves() : pending/completed tasks
                                 (empty in the live snapshot -- see note)
  cycle_count.json            -- cycle_count() : session list (empty --
                                 see note)
  cycle_count_session.json    -- cycle_count_session(<id>), keyed by id
                                 (empty -- no sessions exist yet)
  item_master.json            -- item_master() : full product list
  item_master_detail.json     -- item_master_detail(<sku>), keyed by sku
"""
import csv
import json
import os
from datetime import date, datetime

BASE = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT = r"C:\users\gary\surgi_central\Clone\data\inventory"

SNAPSHOT_DATE = date(2026, 7, 23)

CATEGORIES = [
    ('ENT', 'E'),
    ('ENTVascular', 'EV'),
    ('Endomechanical', 'Y'),
    ('GYN/Urology', 'G'),
    ('GYN/UrologyEndomechanical', 'GY'),
    ('GYN/UrologyMesh', 'MG'),
    ('Hemostat / Wound Care', 'H'),
    ('Hemostat / Wound CareOrthopedicSpine / Neurology', 'SOH'),
    ('Hemostat / Wound CareSpine / Neurology', 'HS'),
    ('Mesh', 'M'),
    ('MeshEndomechanical', 'YM'),
    ('Orthopedic', 'O'),
    ('OrthopedicSpine / Neurology', 'SO'),
    ('OrthopedicSpine / NeurologyEndomechanical', 'YOS'),
    ('Robotics', 'R'),
    ('Specialty', 'Z'),
    ('Spine / Neurology', 'S'),
    ('Vascular', 'V'),
]

TAX_CLASSES = ['P0000000', 'PH404914']


# ── Helpers ───────────────────────────────────────────────────────────────

def read_csv(name):
    path = os.path.join(BASE, name)
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def to_float(v, default=0.0):
    if v is None or v == '':
        return default
    try:
        return float(v)
    except ValueError:
        return default


def to_int(v, default=0):
    return int(to_float(v, default))


def to_bool(v):
    return v == 't'


def parse_date(v):
    if not v:
        return None
    try:
        return datetime.strptime(v[:10], '%Y-%m-%d').date()
    except ValueError:
        return None


def parse_dt_iso(v):
    """Return an ISO-8601 string (kept as string for JSON/JS Date parsing)."""
    if not v:
        return None
    return v.replace(' ', 'T')


# ── Shared loaders ────────────────────────────────────────────────────────

def load_products():
    return {p['sku']: p for p in read_csv('products.csv')}


def load_sku_metrics():
    return {m['ref']: m for m in read_csv('sku_metrics.csv')}


def load_warehouse_locations():
    loc = {}
    for r in read_csv('warehouse_locations.csv'):
        loc[r['item_code'].upper()] = r['location']
    return loc


def load_lots():
    return read_csv('inventory_lots.csv')


def load_holds():
    return read_csv('inventory_holds.csv')


# ── summary() port ────────────────────────────────────────────────────────

def build_summary_json():
    products = load_products()
    sku_metrics = load_sku_metrics()
    wh_locations = load_warehouse_locations()
    lots = load_lots()
    holds = load_holds()

    # Aggregate lots per ref
    agg = {}
    for l in lots:
        ref = l['ref']
        zone = l['zone']
        qty = to_float(l['qty_on_hand'])
        a = agg.setdefault(ref, {'main': 0.0, 'short_dated': 0.0, 'damaged': 0.0, 'total': 0.0})
        if zone == 'main':
            a['main'] += qty
        elif zone == 'short_dated':
            a['short_dated'] += qty
        elif zone == 'damaged':
            a['damaged'] += qty
        a['total'] += qty

    # Holds: regular approved (not expired) and strategic approved
    h_reg = {}
    h_str = {}
    for h in holds:
        if h['hold_type'] == 'regular' and h['status'] == 'approved':
            expires = h.get('expires_at')
            if expires:
                exp_dt = expires[:19]
                try:
                    if datetime.strptime(exp_dt, '%Y-%m-%d %H:%M:%S') <= datetime(2026, 7, 23, 12, 0, 0):
                        continue  # expired -- excluded by NOW() filter
                except ValueError:
                    pass
            h_reg[h['ref']] = h_reg.get(h['ref'], 0.0) + to_float(h['qty'])
        elif h['hold_type'] == 'strategic' and h['status'] == 'approved':
            remaining = to_float(h['qty']) - to_float(h.get('fulfilled_qty'))
            h_str[h['ref']] = h_str.get(h['ref'], 0.0) + remaining

    skus = []
    for ref, a in agg.items():
        p = products.get(ref, {})
        sm = sku_metrics.get(ref, {})
        on_hold = h_reg.get(ref, 0.0)
        strategic_hold = h_str.get(ref, 0.0)
        held = on_hold + strategic_hold
        available_qty = max(0.0, a['main'] - held)

        skus.append({
            'ref': ref,
            'brand': p.get('manufacturer') or '',
            'item_name': p.get('name') or '',
            'main_qty': round(a['main'], 2),
            'short_dated_qty': round(a['short_dated'], 2),
            'damaged_qty': round(a['damaged'], 2),
            'total_qty': round(a['total'], 2),
            'on_hold': round(on_hold, 2),
            'strategic_hold': round(strategic_hold, 2),
            'available_qty': round(available_qty, 2),
            'vel_3mo': to_float(sm.get('vel_3mo')) if sm.get('vel_3mo') not in (None, '') else None,
            'vel_12mo': to_float(sm.get('vel_12mo')) if sm.get('vel_12mo') not in (None, '') else None,
            'min_par': to_float(sm.get('min_par')) if sm.get('min_par') not in (None, '') else None,
            'avg_cost': to_float(sm.get('avg_cost')) if sm.get('avg_cost') not in (None, '') else None,
            'avg_sale_price': to_float(sm.get('avg_sale_price')) if sm.get('avg_sale_price') not in (None, '') else None,
            'wh_location': wh_locations.get(ref.upper(), ''),
        })

    skus.sort(key=lambda s: s['ref'])

    zone_move_tasks = read_csv('zone_move_tasks.csv')
    pending_moves = sum(1 for t in zone_move_tasks if t.get('status') == 'pending')

    return {
        'generated_from_snapshot': SNAPSHOT_DATE.isoformat(),
        'skus': skus,
        'pending_moves': pending_moves,
    }


# ── lot_detail(<ref>) port ────────────────────────────────────────────────

def build_lot_detail_json():
    products = load_products()
    sku_metrics = load_sku_metrics()
    wh_locations = load_warehouse_locations()
    lots = load_lots()
    holds = load_holds()
    movements = read_csv('inventory_movements.csv')  # empty in this snapshot

    by_ref_lots = {}
    for l in lots:
        by_ref_lots.setdefault(l['ref'], []).append(l)

    by_ref_holds = {}
    for h in holds:
        if h['status'] in ('pending', 'approved'):
            by_ref_holds.setdefault(h['ref'], []).append(h)

    by_ref_movements = {}
    for m in movements:
        by_ref_movements.setdefault(m['ref'], []).append(m)

    result = {}
    for ref, ref_lots in by_ref_lots.items():
        ref_lots_sorted = sorted(
            ref_lots,
            key=lambda l: (parse_date(l['exp_date']) is None, parse_date(l['exp_date']) or date.max)
        )
        lots_out = []
        for l in ref_lots_sorted:
            lots_out.append({
                'lot': l.get('lot') or '',
                'exp_date': l['exp_date'] or None,
                'zone': l['zone'],
                'wh_location': wh_locations.get(ref.upper()) or l.get('wh_location') or '',
                'qty_on_hand': round(to_float(l['qty_on_hand']), 2),
                'last_updated': parse_dt_iso(l.get('last_updated')),
            })

        total_qty = sum(to_float(l['qty_on_hand']) for l in ref_lots)
        main_qty = sum(to_float(l['qty_on_hand']) for l in ref_lots if l['zone'] == 'main')
        short_dated_qty = sum(to_float(l['qty_on_hand']) for l in ref_lots if l['zone'] == 'short_dated')
        damaged_qty = sum(to_float(l['qty_on_hand']) for l in ref_lots if l['zone'] == 'damaged')

        ref_holds = by_ref_holds.get(ref, [])
        held_qty = sum(to_float(h['qty']) for h in ref_holds if h['status'] == 'approved')
        available_qty = max(0.0, main_qty - held_qty)

        holds_out = [{
            'hold_type': h['hold_type'],
            'customer_name': h.get('customer_name') or '',
            'sales_rep': h.get('sales_rep') or '',
            'qty': round(to_float(h['qty']), 2),
            'fulfilled_qty': round(to_float(h.get('fulfilled_qty')), 2),
            'expires_at': parse_dt_iso(h.get('expires_at')),
            'status': h['status'],
        } for h in ref_holds]

        p = products.get(ref, {})
        sm = sku_metrics.get(ref, {})

        result[ref] = {
            'ref': ref,
            'product': {
                'manufacturer': p.get('manufacturer') or '',
                'name': p.get('name') or '',
            } if p else None,
            'metrics': {
                'vel_3mo': to_float(sm.get('vel_3mo')) if sm.get('vel_3mo') not in (None, '') else None,
                'vel_12mo': to_float(sm.get('vel_12mo')) if sm.get('vel_12mo') not in (None, '') else None,
                'min_par': to_float(sm.get('min_par')) if sm.get('min_par') not in (None, '') else None,
            } if sm else None,
            'lots': lots_out,
            'movements': [],  # empty in this snapshot -- inventory_movements has no rows yet
            'holds': holds_out,
            'total_qty': round(total_qty, 2),
            'main_qty': round(main_qty, 2),
            'short_dated_qty': round(short_dated_qty, 2),
            'damaged_qty': round(damaged_qty, 2),
            'available_qty': round(available_qty, 2),
        }

    return result


# ── holds() port ─────────────────────────────────────────────────────────

def build_holds_json():
    holds = load_holds()
    holds_sorted = sorted(holds, key=lambda h: h['created_at'], reverse=True)
    out = []
    for h in holds_sorted:
        out.append({
            'id': to_int(h['id']),
            'ref': h['ref'],
            'hold_type': h['hold_type'],
            'qty': round(to_float(h['qty']), 2),
            'customer_name': h.get('customer_name') or '',
            'sales_rep': h.get('sales_rep') or '',
            'reason': h.get('reason') or '',
            'status': h['status'],
            'requested_by': h.get('requested_by') or '',
            'expires_at': parse_dt_iso(h.get('expires_at')),
            'guaranteed_by_date': h.get('guaranteed_by_date') or None,
            'guaranteed_qty': to_float(h.get('guaranteed_qty')) if h.get('guaranteed_qty') else None,
            'fulfilled_qty': round(to_float(h.get('fulfilled_qty')), 2),
            'rep_status': h.get('rep_status') or '',
            'created_at': parse_dt_iso(h.get('created_at')),
        })
    return {'holds': out}


# ── zone_moves() port (empty snapshot) ──────────────────────────────────

def build_zone_moves_json():
    tasks = read_csv('zone_move_tasks.csv')
    pending = [t for t in tasks if t.get('status') == 'pending']
    completed = [t for t in tasks if t.get('status') == 'completed']
    return {
        'pending': pending,
        'completed': completed,
        'pending_count': len(pending),
        'note': 'zone_move_tasks table has no rows in the 2026-07-23 snapshot '
                '-- this feature had not generated any tasks yet at capture time.',
    }


# ── cycle_count() / cycle_count_session() ports (empty snapshot) ───────

def build_cycle_count_json():
    sessions = read_csv('cycle_count_sessions.csv')
    return {
        'sessions': sessions,
        'note': 'cycle_count_sessions table has no rows in the 2026-07-23 snapshot '
                '-- no sessions had been run yet at capture time.',
    }


def build_cycle_count_session_json():
    items = read_csv('cycle_count_items.csv')
    return {'by_session': {}, 'items_raw_count': len(items)}


# ── item_master() / item_master_detail() ports ──────────────────────────

def build_item_master_json():
    products = read_csv('products.csv')
    sku_metrics = load_sku_metrics()
    lots = load_lots()

    qty_by_ref = {}
    for l in lots:
        qty_by_ref[l['ref']] = qty_by_ref.get(l['ref'], 0.0) + to_float(l['qty_on_hand'])

    out = []
    for p in products:
        sku = p['sku']
        sm = sku_metrics.get(sku, {})
        out.append({
            'id': to_int(p['id']),
            'sku': sku,
            'name': p.get('name') or '',
            'manufacturer': p.get('manufacturer') or '',
            'item_number': p.get('item_number') or '',
            'category_code': p.get('category_code') or '',
            'tax_class': p.get('tax_class') or '',
            'retail_price': to_float(p.get('retail_price')) if p.get('retail_price') else None,
            'true_low': to_float(p.get('true_low')) if p.get('true_low') else None,
            'approval_only': to_float(p.get('approval_only')) if p.get('approval_only') else None,
            'implantable': to_bool(p.get('implantable')),
            'temp_critical': to_bool(p.get('temp_critical')),
            'temp_sensitive': to_bool(p.get('temp_sensitive')),
            'is_active': to_bool(p.get('is_active')),
            'total_qty': round(qty_by_ref.get(sku, 0.0), 2),
            'avg_cost': to_float(sm.get('avg_cost')) if sm.get('avg_cost') else None,
        })
    out.sort(key=lambda p: p['sku'])

    return {
        'products': out,
        'categories': CATEGORIES,
        'tax_classes': TAX_CLASSES,
    }


def build_item_master_detail_json():
    products = load_products()
    sku_metrics = load_sku_metrics()
    lots = load_lots()
    competitor_products = read_csv('competitor_products.csv')
    competitors_rows = read_csv('competitors.csv')
    competitor_names = {c['id']: c['name'] for c in competitors_rows}

    qty_by_ref = {}
    for l in lots:
        ref = l['ref']
        zone = l['zone']
        qty = to_float(l['qty_on_hand'])
        a = qty_by_ref.setdefault(ref, {'main': 0.0, 'short_dated': 0.0, 'damaged': 0.0, 'total': 0.0})
        a['total'] += qty
        if zone == 'main':
            a['main'] += qty
        elif zone == 'short_dated':
            a['short_dated'] += qty
        elif zone == 'damaged':
            a['damaged'] += qty

    # item_number -> in-stock, priced competitor rows, ascending price
    comp_by_item_number = {}
    for cp in competitor_products:
        qty = to_int(cp.get('qty_available'), 0)
        price = cp.get('price')
        if qty <= 0 or not price:
            continue
        item_no = cp.get('sku') or ''
        comp_by_item_number.setdefault(item_no.upper(), []).append({
            'competitor': competitor_names.get(cp.get('competitor_id'), 'Unknown'),
            'price': round(to_float(price), 2),
            'qty_available': qty,
            'last_seen': parse_dt_iso(cp.get('last_seen')),
        })
    for k in comp_by_item_number:
        comp_by_item_number[k].sort(key=lambda r: r['price'])

    result = {}
    for sku, p in products.items():
        sm = sku_metrics.get(sku, {})
        q = qty_by_ref.get(sku, {'main': 0.0, 'short_dated': 0.0, 'damaged': 0.0, 'total': 0.0})

        item_number = p.get('item_number') or ''
        competitor_prices = comp_by_item_number.get(item_number.upper(), []) if item_number else []

        result[sku] = {
            'product': {
                'sku': sku,
                'name': p.get('name') or '',
                'manufacturer': p.get('manufacturer') or '',
                'item_number': item_number,
                'gtin': p.get('gtin') or '',
                'uom': p.get('uom') or '',
                'conversion': p.get('conversion') or '',
                'category_code': p.get('category_code') or '',
                'tax_class': p.get('tax_class') or '',
                'retail_price': to_float(p.get('retail_price')) if p.get('retail_price') else None,
                'sale_price': to_float(p.get('sale_price')) if p.get('sale_price') else None,
                'true_low': to_float(p.get('true_low')) if p.get('true_low') else None,
                'approval_only': to_float(p.get('approval_only')) if p.get('approval_only') else None,
                'implantable': to_bool(p.get('implantable')),
                'temp_critical': to_bool(p.get('temp_critical')),
                'temp_sensitive': to_bool(p.get('temp_sensitive')),
                'is_active': to_bool(p.get('is_active')),
            },
            'metrics': {
                'avg_cost': to_float(sm.get('avg_cost')) if sm.get('avg_cost') else None,
                'avg_sale_price': to_float(sm.get('avg_sale_price')) if sm.get('avg_sale_price') else None,
                'vel_3mo': to_float(sm.get('vel_3mo')) if sm.get('vel_3mo') not in (None, '') else None,
                'vel_12mo': to_float(sm.get('vel_12mo')) if sm.get('vel_12mo') not in (None, '') else None,
                'min_par': to_float(sm.get('min_par')) if sm.get('min_par') not in (None, '') else None,
            } if sm else None,
            'qty': {
                'total_qty': round(q['total'], 2),
                'main_qty': round(q['main'], 2),
                'short_dated_qty': round(q['short_dated'], 2),
                'damaged_qty': round(q['damaged'], 2),
            },
            'competitor_prices': competitor_prices,
        }

    return {
        'by_sku': result,
        'categories': CATEGORIES,
        'tax_classes': TAX_CLASSES,
    }


def dump(name, obj):
    path = os.path.join(OUT, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, separators=(',', ':'))
    print(f"{name}: {os.path.getsize(path):,} bytes")


def main():
    os.makedirs(OUT, exist_ok=True)

    dump('summary.json', build_summary_json())
    dump('lot_detail.json', build_lot_detail_json())
    dump('holds.json', build_holds_json())
    dump('zone_moves.json', build_zone_moves_json())
    dump('cycle_count.json', build_cycle_count_json())
    dump('cycle_count_session.json', build_cycle_count_session_json())
    dump('item_master.json', build_item_master_json())
    dump('item_master_detail.json', build_item_master_detail_json())


if __name__ == '__main__':
    main()
