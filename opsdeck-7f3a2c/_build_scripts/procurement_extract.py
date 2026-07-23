"""
Extraction script for the Procurement module (static demo).

Reads the raw Postgres CSV dump (../../_raw_db_backup_2026-07-23/*.csv) and
reproduces the exact logic of surgicentral/procurement/routes.py
(_load_items, _build_stats, index(), competitor_intel(), competitor_detail())
using nothing but the stdlib csv/json modules, then writes static JSON for
the Clone/procurement/*.html pages to fetch.

Outputs:
  Clone/data/procurement/index.json            -- dashboard (all tabs)
  Clone/data/procurement/competitor_intel.json -- competitor intel table
  Clone/data/procurement/competitor_detail.json -- price-history popup data,
                                                    keyed by "REF|UNIT"
"""
import csv
import json
import os
from datetime import date, datetime

BASE = r"C:\users\gary\surgi_central\_raw_db_backup_2026-07-23"
OUT = r"C:\users\gary\surgi_central\Clone\data\procurement"

# Snapshot date the raw CSV dump was taken -- stands in for date.today() /
# NOW() in the live app, since this is a frozen static copy.
SNAPSHOT_DATE = date(2026, 7, 23)
SNAPSHOT_DT = datetime(2026, 7, 23, 12, 0, 0)

EXCLUDE_NAMES = {
    'sales tax', 'default for unmatched products',
    'partial refund', 'full refund', 'wire',
}

# ── Ported verbatim from procurement/routes.py ──────────────────────────────

RISK_ORDER = {
    'OUT OF STOCK - BUY ON SIGHT':  0,
    'OUT OF STOCK - HIGH PRIORITY': 1,
    'LOW STOCK - PRIORITY ITEM':    2,
    'OUT OF STOCK - REORDER NOW':   3,
    'OUT OF STOCK':                 4,
    'CRITICAL - EXPIRING':          5,
    'URGENT - EXPIRING':            6,
    'WARNING - EXPIRING':           7,
    'OVERSTOCKED':                  8,
    'OK':                           9,
    'ZERO STOCK - NO SALES':        10,
}

RISK_COLORS = {
    'OUT OF STOCK - BUY ON SIGHT':  {'bg': '#FFA500', 'text': '#000'},
    'OUT OF STOCK - HIGH PRIORITY': {'bg': '#FFD700', 'text': '#000'},
    'LOW STOCK - PRIORITY ITEM':    {'bg': '#C9B3E8', 'text': '#000'},
    'OUT OF STOCK - REORDER NOW':   {'bg': '#0D6EFD', 'text': '#fff'},
    'OUT OF STOCK':                 {'bg': '#9EC5FE', 'text': '#000'},
    'CRITICAL - EXPIRING':          {'bg': '#dc3545', 'text': '#fff'},
    'URGENT - EXPIRING':            {'bg': '#fd7e14', 'text': '#fff'},
    'WARNING - EXPIRING':           {'bg': '#ffc107', 'text': '#000'},
    'OVERSTOCKED':                  {'bg': '#fff3cd', 'text': '#000'},
    'OK':                           {'bg': '#d4edda', 'text': '#000'},
    'ZERO STOCK - NO SALES':        {'bg': '#e9ecef', 'text': '#000'},
}

BUCKET_COLORS = {
    'A': '#dc3545',
    'B': '#fd7e14',
    'C': '#0D6EFD',
    'D': '#6c757d',
}

COMP_ALERT_ORDER = {
    'DANGER':      0,
    'LIQUIDATION': 1,
    'OPPORTUNITY': 2,
    'SURGI_ONLY':  3,
    'OK':          4,
    'UNMATCHED':   5,
}

COMP_ALERT_COLORS = {
    'DANGER':      {'bg': '#dc3545', 'text': '#fff'},
    'LIQUIDATION': {'bg': '#fd7e14', 'text': '#fff'},
    'OPPORTUNITY': {'bg': '#198754', 'text': '#fff'},
    'SURGI_ONLY':  {'bg': '#0D6EFD', 'text': '#fff'},
    'OK':          {'bg': '#d4edda', 'text': '#000'},
    'UNMATCHED':   {'bg': '#e9ecef', 'text': '#000'},
}


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


def parse_dt(v):
    if not v:
        return None
    try:
        # e.g. 2026-06-15 14:53:06.112277+00
        return datetime.strptime(v[:19], '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


# ── Load base data ───────────────────────────────────────────────────────

def load_products():
    return {p['sku']: p for p in read_csv('products.csv')}


def load_stock_and_exp():
    """Aggregate inventory_lots.csv into per-ref stock + earliest expiration,
    matching the correlated subqueries in _load_items()."""
    stock_by_ref = {}
    exp_by_ref = {}
    for l in read_csv('inventory_lots.csv'):
        ref = l['ref']
        qty = to_float(l['qty_on_hand'])
        zone = l['zone']
        if zone in ('main', 'short_dated') and qty > 0:
            stock_by_ref[ref] = stock_by_ref.get(ref, 0.0) + qty
        exp = parse_date(l['exp_date'])
        if qty > 0 and exp:
            cur = exp_by_ref.get(ref)
            if cur is None or exp < cur:
                exp_by_ref[ref] = exp
    return stock_by_ref, exp_by_ref


# ── _load_items() port ──────────────────────────────────────────────────

def load_items():
    products = load_products()
    stock_by_ref, exp_by_ref = load_stock_and_exp()

    items = []
    for sm in read_csv('sku_metrics.csv'):
        ref = sm['ref']
        p = products.get(ref)
        if not p:
            continue
        if not to_bool(p.get('is_active')):
            continue
        name = (p.get('name') or '').strip()
        if name.lower() in EXCLUDE_NAMES:
            continue
        if name.upper().startswith('SHIP'):
            continue

        brand = p.get('manufacturer') or p.get('name') or ref
        bucket = (sm.get('bucket') or '').strip() or None
        risk = sm.get('risk_status') or 'OK'
        reorder = sm.get('reorder_rec') or 'NORMAL'

        stock = stock_by_ref.get(ref, 0.0)
        cogs = to_float(sm.get('avg_cost'))
        retail = to_float(p.get('retail_price'))
        sale = to_float(p.get('sale_price'))
        gp = to_float(sm.get('gross_profit_12mo'))
        rev = to_float(sm.get('revenue_12mo'))
        vel_6mo = to_float(sm.get('vel_6mo'))

        approved_price = sale if sale else retail
        inv_value_cost = round(stock * cogs, 2)
        inv_value_retail = round(stock * retail, 2) if retail else 0
        profit_per_month = round(gp / 12.0, 2)

        mos_raw = sm.get('months_of_stock')
        months_of_stock = float(mos_raw) if mos_raw not in (None, '') else 999.0

        exp = exp_by_ref.get(ref)
        if exp and stock > 0:
            days = (exp - SNAPSHOT_DATE).days
            days_to_exp = days
            days_to_removal = max(0, days - 30)
        else:
            days_to_exp = None
            days_to_removal = None

        at_risk = to_float(sm.get('at_risk_units'))
        critical_units = to_float(sm.get('critical_units'))

        action = ''
        if stock > 0 and days_to_exp is not None and days_to_exp <= 180:
            if vel_6mo == 0:
                action = 'LIQUIDATE — No sales history'
            elif at_risk > stock * 0.50:
                action = 'DEEP DISCOUNT needed'
            elif at_risk > 0:
                action = 'DISCOUNT to accelerate'
            else:
                action = 'MONITOR — should sell through'

        risk_bg = RISK_COLORS.get(risk, {}).get('bg', '#e9ecef')
        risk_text = RISK_COLORS.get(risk, {}).get('text', '#000')
        bucket_color = BUCKET_COLORS.get(bucket or '', '#adb5bd')

        items.append({
            'sku': ref,
            'brand': brand,
            'name': p.get('name'),
            'bucket': bucket,
            'risk': risk,
            'reorder': reorder,
            'vel_6mo': round(vel_6mo, 4),
            'vel_6mo_sd': round(to_float(sm.get('vel_6mo_short_dated')), 4),
            'vel_6mo_rd': round(to_float(sm.get('vel_6mo_rep_discount')), 4),
            'vel_3mo': round(to_float(sm.get('vel_3mo')), 4),
            'vel_12mo': round(to_float(sm.get('vel_12mo')), 4),
            'sold_12mo': round(to_float(sm.get('sold_12mo')), 4),
            'trend_pct': round(to_float(sm.get('trend_pct')), 4),
            'months_of_stock': round(months_of_stock, 2),
            'at_risk': round(at_risk, 4),
            'critical_units': round(critical_units, 4),
            'cogs': round(cogs, 4),
            'avg_rate': round(to_float(sm.get('avg_sale_price')), 4),
            'revenue_12mo': round(rev, 2),
            'gross_profit_12mo': round(gp, 2),
            'margin_pct': round(to_float(sm.get('actual_margin_pct')), 6),
            'units_sd_6mo': round(to_float(sm.get('units_short_dated_6mo')), 4),
            'units_rd_6mo': round(to_float(sm.get('units_rep_discount_6mo')), 4),
            'retail_price': round(retail, 2),
            'sale_price': round(sale, 2),
            'stock': round(stock, 2),
            'earliest_exp': exp.isoformat() if exp else None,
            'approved_price': round(approved_price, 2),
            'inv_value_cost': inv_value_cost,
            'inv_value_retail': inv_value_retail,
            'profit_per_month': profit_per_month,
            'days_to_exp': days_to_exp,
            'days_to_removal': days_to_removal,
            'action': action,
            'risk_bg': risk_bg,
            'risk_text': risk_text,
            'bucket_color': bucket_color,
        })

    items.sort(key=lambda x: (
        RISK_ORDER.get(x['risk'], 99),
        {'A': 0, 'B': 1, 'C': 2, 'D': 3}.get(x['bucket'] or '', 4),
        -x['vel_6mo'],
        -x['stock'],
    ))
    return items


def build_stats(items):
    return {
        'total_skus': len(items),
        'oos_count': sum(1 for i in items if i['stock'] == 0 and i['vel_6mo'] > 0),
        'expiring_count': sum(1 for i in items if i['days_to_exp'] is not None and i['days_to_exp'] <= 180),
        'critical_count': sum(1 for i in items if i['days_to_exp'] is not None and i['days_to_exp'] <= 30),
        'bucket_a_count': sum(1 for i in items if i['bucket'] == 'A'),
        'bucket_b_count': sum(1 for i in items if i['bucket'] == 'B'),
        'total_units_on_shelf': sum(i['stock'] for i in items),
        'at_risk_units': sum(i['at_risk'] for i in items if i['at_risk'] > 0),
        'dead_capital': sum(i['inv_value_cost'] for i in items if i['vel_6mo'] == 0 and i['stock'] > 0),
        'at_risk_value': sum(i['at_risk'] * i['cogs'] for i in items if i['at_risk'] > 0),
        'total_inv_cost': sum(i['inv_value_cost'] for i in items),
        'gp_12mo': sum(i['gross_profit_12mo'] for i in items),
        'revenue_12mo': sum(i['revenue_12mo'] for i in items),
    }


def build_index_json(items):
    stats = build_stats(items)

    risk_counts = {}
    for i in items:
        risk_counts[i['risk']] = risk_counts.get(i['risk'], 0) + 1

    bucket_counts = {}
    bucket_gp = {}
    for i in items:
        b = i['bucket'] or ''
        bucket_counts[b] = bucket_counts.get(b, 0) + 1
        bucket_gp[b] = bucket_gp.get(b, 0.0) + i['gross_profit_12mo']

    top_profit_skus = [i['sku'] for i in sorted(items, key=lambda x: -x['profit_per_month'])[:10]]

    buy_list_skus = [i['sku'] for i in items
                     if i['reorder'] not in ('NORMAL', 'DO NOT REORDER', 'NO SALES - REVIEW', 'HOLD - SUFFICIENT STOCK')
                     and i['reorder'] != '']
    oos_skus = [i['sku'] for i in items if i['stock'] == 0]

    expiring_items = [i for i in items if i['days_to_exp'] is not None and i['days_to_exp'] <= 180]
    expiring_items.sort(key=lambda x: x['days_to_exp'])
    expiring_skus = [i['sku'] for i in expiring_items]

    dnr_skus = [i['sku'] for i in items if i['reorder'] in ('DO NOT REORDER', 'NO SALES - REVIEW')]

    profitability_skus = [i['sku'] for i in sorted(items, key=lambda x: -x['gross_profit_12mo'])[:500]]

    dead_capital_items = sorted(
        [i for i in items if i['vel_6mo'] == 0 and i['stock'] > 0],
        key=lambda x: -x['inv_value_cost']
    )
    dead_capital_skus = [i['sku'] for i in dead_capital_items]

    return {
        'generated_from_snapshot': SNAPSHOT_DATE.isoformat(),
        'items': items,
        'stats': stats,
        'risk_counts': risk_counts,
        'bucket_counts': bucket_counts,
        'bucket_gp': bucket_gp,
        'risk_order': list(RISK_ORDER.keys()),
        'risk_colors': RISK_COLORS,
        'bucket_colors': BUCKET_COLORS,
        # Tabs are stored as ordered SKU lists (not duplicated item dicts) --
        # the page builds a sku->item lookup from `items` once and renders
        # each tab by mapping these lists through it. Mirrors the real
        # route's separate filtered/sorted sub-lists without repeating
        # ~25 fields x thousands of rows x 7 tabs in the JSON payload.
        'top_profit_skus': top_profit_skus,
        'buy_list_skus': buy_list_skus,
        'oos_skus': oos_skus,
        'expiring_skus': expiring_skus,
        'dnr_skus': dnr_skus,
        'profitability_skus': profitability_skus,
        'dead_capital_skus': dead_capital_skus,
    }


# ── competitor_intel() port ──────────────────────────────────────────────

def build_competitor_intel_json():
    products = load_products()
    sku_metrics = {sm['ref']: sm for sm in read_csv('sku_metrics.csv')}
    competitors_rows = read_csv('competitors.csv')
    competitors = {int(c['id']): c['name'] for c in competitors_rows}

    # sku_map: (BASE_REF upper, unit_type) -> our_sku  (primary match)
    sku_map_rows = read_csv('sku_map.csv')
    sku_map_by_base_unit = {}
    sku_map_by_our_sku = {}
    for m in sku_map_rows:
        key = (m['base_ref'].upper(), m['unit_type'])
        sku_map_by_base_unit[key] = m['our_sku']
        sku_map_by_our_sku[m['our_sku']] = m

    # fallback: item_number -> list of active products (with sku_map info),
    # ordered later by unit_type match preference
    products_by_item_number = {}
    for sku, p in products.items():
        item_no = p.get('item_number')
        if item_no and to_bool(p.get('is_active')):
            products_by_item_number.setdefault(item_no, []).append(p)

    competitor_products = read_csv('competitor_products.csv')

    grouped = {}
    for cp in competitor_products:
        comp_sku = cp['sku'] or ''
        comp_unit = cp['unit_type'] or 'E'
        competitor_id = int(cp['competitor_id']) if cp['competitor_id'] else None

        # Primary: sku_map unit-type aware
        our_sku = sku_map_by_base_unit.get((comp_sku.upper(), comp_unit))
        p_m = products.get(our_sku) if our_sku else None

        p_f = None
        if not p_m:
            # Fallback: item_number match (exact, case-sensitive per real SQL),
            # prefer product whose sku_map.unit_type matches comp_unit
            candidates = products_by_item_number.get(comp_sku, [])
            if candidates:
                def sort_key(prod):
                    sm2 = sku_map_by_our_sku.get(prod['sku'])
                    prod_unit = (sm2['unit_type'] if sm2 else 'E') or 'E'
                    return 0 if prod_unit == comp_unit else 1
                p_f = sorted(candidates, key=sort_key)[0]

        matched = p_m or p_f
        our_sku_final = matched['sku'] if matched else None
        our_name = matched.get('name') if matched else None
        our_mfr = (matched.get('manufacturer') or '') if matched else ''

        sm_f = sku_map_by_our_sku.get(our_sku_final) if our_sku_final else None
        our_unit = (sm_f['unit_type'] if sm_f else 'E') or 'E'
        our_units_pkg = int(to_float(sm_f['units_per_pkg'])) if sm_f and sm_f.get('units_per_pkg') else 1

        skm = sku_metrics.get(our_sku_final) if our_sku_final else None
        our_cogs = to_float(skm.get('avg_cost')) if skm else 0.0
        our_retail = to_float(matched.get('retail_price')) if matched else 0.0
        our_sale = to_float(matched.get('sale_price')) if matched else 0.0
        vel_6mo = to_float(skm.get('vel_6mo')) if skm else 0.0
        bucket = (skm.get('bucket') or '').strip() or None if skm else None
        risk = skm.get('risk_status') if skm else None

        key = (comp_sku, comp_unit, our_sku_final)
        if key not in grouped:
            grouped[key] = {
                'comp_ref': comp_sku,
                'comp_mfr': cp.get('manufacturer'),
                'comp_name': cp.get('name'),
                'comp_unit': comp_unit,
                'comp_units_pkg': to_int(cp.get('units_per_pkg'), 1) or 1,
                'our_sku': our_sku_final,
                'our_name': our_name,
                'our_mfr': our_mfr,
                'our_unit': our_unit,
                'our_units_pkg': our_units_pkg or 1,
                'our_cogs': round(our_cogs, 4),
                'our_retail': round(our_retail, 2),
                'our_sale': round(our_sale, 2),
                'vel_6mo': round(vel_6mo, 4),
                'bucket': bucket,
                'risk': risk,
                'comp_ids': {},
            }
        if competitor_id:
            grouped[key]['comp_ids'][competitor_id] = {
                'cp_id': int(cp['id']),
                'price': round(to_float(cp.get('price')), 4),
                'qty': to_int(cp.get('qty_available'), 0),
                'url': cp.get('url') or '',
            }

    all_rows = []
    for item in grouped.values():
        our_cogs = item['our_cogs']
        our_retail = item['our_retail'] or item['our_sale']
        comp_prices = [v['price'] for v in item['comp_ids'].values() if v['price'] > 0]
        comp_stock = any(v['qty'] > 0 for v in item['comp_ids'].values())
        min_comp = min(comp_prices) if comp_prices else 0

        if not item['our_sku']:
            alert = 'UNMATCHED'
        elif not comp_prices:
            alert = 'SURGI_ONLY'
        elif our_cogs > 0 and min_comp > 0 and comp_stock and min_comp < our_cogs * 0.70:
            alert = 'LIQUIDATION'
        elif our_cogs > 0 and min_comp > 0 and comp_stock and min_comp < our_cogs:
            alert = 'DANGER'
        elif our_retail > 0 and min_comp > 0 and comp_stock and min_comp > our_retail * 1.10:
            alert = 'OPPORTUNITY'
        else:
            alert = 'OK'

        item['alert'] = alert
        item['alert_bg'] = COMP_ALERT_COLORS.get(alert, {}).get('bg', '#e9ecef')
        item['alert_text'] = COMP_ALERT_COLORS.get(alert, {}).get('text', '#000')
        item['bucket_color'] = BUCKET_COLORS.get(item['bucket'] or '', '#adb5bd')
        all_rows.append(item)

    display_rows = [r for r in all_rows if r['alert'] != 'UNMATCHED']
    unmatched_count = sum(1 for r in all_rows if r['alert'] == 'UNMATCHED')

    display_rows.sort(key=lambda x: (
        COMP_ALERT_ORDER.get(x['alert'], 99),
        x['comp_ref'] or '',
    ))

    comp_stats = {
        'total': len(display_rows),
        'unmatched_total': unmatched_count,
        'danger': sum(1 for r in display_rows if r['alert'] == 'DANGER'),
        'liquidation': sum(1 for r in display_rows if r['alert'] == 'LIQUIDATION'),
        'opportunity': sum(1 for r in display_rows if r['alert'] == 'OPPORTUNITY'),
        'surgi_only': sum(1 for r in display_rows if r['alert'] == 'SURGI_ONLY'),
    }

    return {
        'rows': display_rows,
        'stats': comp_stats,
        'competitors': competitors,
        'alert_colors': COMP_ALERT_COLORS,
        'bucket_colors': BUCKET_COLORS,
    }, display_rows


# ── competitor_detail() port (pre-extracted for all displayed rows) ─────

def build_competitor_detail_json(display_rows):
    """Reproduce competitor_detail(): price history (last 90 days) per
    (comp_ref, comp_unit) across ALL competitors, plus our monthly sales
    (last 12 months) for the matched our_sku -- but pre-computed only for
    the (ref, unit) pairs that actually appear in the competitor_intel page
    (UNMATCHED rows are hidden and never clicked), per _BUILD_CONVENTIONS.md.
    """
    needed_keys = set()
    needed_our_skus = set()
    for r in display_rows:
        needed_keys.add((r['comp_ref'].upper(), r['comp_unit']))
        if r['our_sku']:
            needed_our_skus.add(r['our_sku'])

    competitor_products = read_csv('competitor_products.csv')
    competitors_rows = read_csv('competitors.csv')
    competitor_names = {int(c['id']): c['name'] for c in competitors_rows}

    # id -> (sku upper, unit_type, competitor_id) for rows we need history for
    needed_cp_ids = {}
    for cp in competitor_products:
        key = ((cp['sku'] or '').upper(), cp['unit_type'] or 'E')
        if key in needed_keys:
            needed_cp_ids[int(cp['id'])] = key

    cutoff_dt = SNAPSHOT_DT.timestamp() - 90 * 86400

    # price_history[(ref,unit)][competitor_name] = [{dt,price,qty}, ...]
    price_history = {}
    with open(os.path.join(BASE, 'competitor_price_history.csv'), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            cp_id = int(row['competitor_product_id'])
            key = needed_cp_ids.get(cp_id)
            if not key:
                continue
            dt = parse_dt(row['recorded_at'])
            if not dt or dt.timestamp() < cutoff_dt:
                continue
            # find which competitor this cp_id belongs to
            comp_name = None
            # (looked up lazily below via cp_to_competitor map)
            price_history.setdefault(key, {})
            entry = {'dt': dt.date().isoformat(), 'price': round(to_float(row['price']), 4),
                     'qty': to_int(row['qty_available'], 0)}
            price_history[key].setdefault('__rows__', []).append((cp_id, entry))

    # Build cp_id -> competitor_id map (only for needed ids, cheap second pass)
    cp_to_competitor = {}
    for cp in competitor_products:
        cid = int(cp['id'])
        if cid in needed_cp_ids:
            cp_to_competitor[cid] = int(cp['competitor_id']) if cp['competitor_id'] else None

    final_history = {}
    for key, obj in price_history.items():
        by_comp = {}
        for cp_id, entry in obj.get('__rows__', []):
            comp_id = cp_to_competitor.get(cp_id)
            comp_name = competitor_names.get(comp_id, 'Unknown')
            by_comp.setdefault(comp_name, []).append(entry)
        for comp_name in by_comp:
            by_comp[comp_name].sort(key=lambda e: e['dt'])
        final_history[f"{key[0]}|{key[1]}"] = by_comp

    # our_sales: monthly qty/avg_rate/revenue per matched our_sku, last 12mo
    products = load_products()
    product_id_to_sku = {p['id']: sku for sku, p in products.items()}
    skus_to_check = needed_our_skus

    sales_agg = {}  # sku -> {month: [qty_sum, rate_sum, rate_count, revenue_sum]}
    cutoff_date = date(2026, 7, 23).toordinal() - 365  # ~12 months back
    cutoff_date = date.fromordinal(cutoff_date)

    with open(os.path.join(BASE, 'sales_history.csv'), newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            sku = product_id_to_sku.get(row['product_id'])
            if not sku or sku not in skus_to_check:
                continue
            qty = to_float(row['quantity'])
            if qty <= 0:
                continue
            sd = parse_date(row['sale_date'])
            if not sd or sd < cutoff_date:
                continue
            p = products.get(sku, {})
            name = (p.get('name') or '').strip()
            if name.lower() in EXCLUDE_NAMES or name.upper().startswith('SHIP'):
                continue
            month = sd.replace(day=1).isoformat()
            rate = to_float(row['rate'])
            bucket_key = (sku, month)
            agg = sales_agg.setdefault(bucket_key, {'qty': 0.0, 'rate_sum': 0.0, 'rate_n': 0, 'revenue': 0.0})
            agg['qty'] += qty
            agg['rate_sum'] += rate
            agg['rate_n'] += 1
            agg['revenue'] += qty * rate

    our_sales_by_sku = {}
    for (sku, month), agg in sales_agg.items():
        our_sales_by_sku.setdefault(sku, []).append({
            'month': month,
            'qty': round(agg['qty'], 2),
            'avg_rate': round(agg['rate_sum'] / agg['rate_n'], 4) if agg['rate_n'] else 0,
            'revenue': round(agg['revenue'], 2),
        })
    for sku in our_sales_by_sku:
        our_sales_by_sku[sku].sort(key=lambda m: m['month'])

    # Final payload keyed by "REF|UNIT" (matches JS lookup: `${ref}|${unit}`)
    detail = {}
    for key_str, by_comp in final_history.items():
        detail.setdefault(key_str, {'price_history': by_comp, 'our_sales': []})
    # Attach our_sales per (ref,unit) row (a given ref|unit can map to at most
    # one our_sku per the grouping key used on the intel page)
    for r in display_rows:
        key_str = f"{r['comp_ref'].upper()}|{r['comp_unit']}"
        if key_str not in detail:
            detail[key_str] = {'price_history': {}, 'our_sales': []}
        if r['our_sku'] and r['our_sku'] in our_sales_by_sku:
            detail[key_str]['our_sales'] = our_sales_by_sku[r['our_sku']]
        elif 'our_sales' not in detail[key_str]:
            detail[key_str]['our_sales'] = []

    return detail


def main():
    os.makedirs(OUT, exist_ok=True)

    items = load_items()
    index_json = build_index_json(items)
    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index_json, f, separators=(',', ':'))
    print(f"index.json: {len(items)} items, "
          f"{os.path.getsize(os.path.join(OUT, 'index.json')):,} bytes")

    ci_json, display_rows = build_competitor_intel_json()
    with open(os.path.join(OUT, 'competitor_intel.json'), 'w', encoding='utf-8') as f:
        json.dump(ci_json, f, separators=(',', ':'))
    print(f"competitor_intel.json: {len(display_rows)} rows, "
          f"{os.path.getsize(os.path.join(OUT, 'competitor_intel.json')):,} bytes")

    detail_json = build_competitor_detail_json(display_rows)
    with open(os.path.join(OUT, 'competitor_detail.json'), 'w', encoding='utf-8') as f:
        json.dump(detail_json, f, separators=(',', ':'))
    print(f"competitor_detail.json: {len(detail_json)} keys, "
          f"{os.path.getsize(os.path.join(OUT, 'competitor_detail.json')):,} bytes")


if __name__ == '__main__':
    main()
