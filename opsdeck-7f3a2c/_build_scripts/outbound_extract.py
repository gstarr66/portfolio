"""
Extraction script for the Outbound module of the SurgiCentral static demo.

Reads the raw Postgres CSV dump (../../_raw_db_backup_2026-07-23/) and
reproduces the query logic in surgicentral/outbound/routes.py to produce
static JSON consumed by Clone/outbound/*.html.

Outputs:
  Clone/data/outbound/orders.json    -- dashboard.html, pull/pack/ship/packing_slip
  Clone/data/outbound/invoices.json  -- invoices.html (Invoice Approver)

Only stdlib (csv, json) is used -- no pandas needed for datasets this small.

Data-shape note: products.csv has zero rows with true_low or approval_only
set in this snapshot, so the True-Low / Approval-Only pricing-alert badges
on invoices.html are computed faithfully (same subquery logic as
outbound/routes.py dispatch_invoices) but will always evaluate to zero
violations against this data. The per-line price-check modal in the real
app is therefore not wired up as a fetch in the demo -- Approve/Deny/
Restore/Sync are all data-demo-inert per _BUILD_CONVENTIONS.md, and since
there is no violation data to show, the modal's business value is already
covered by the (empty) badge columns in the table itself.

The pack -> ship -> packing_slip fake-live flow is demoed on order id 10
(daily_order_number 10, invoice 41488, Unity Physicians Hospital) -- picked
because it is 'approved' status (a valid starting point for the full
pull->pack->ship walk) and has a complete multi-line ship_addr + ship_to_name
for a realistic packing slip. The pages are written generically (?order=<id>
query string + client-side JSON lookup) so all 15 real orders are browsable;
demoStore only intercepts writes for whichever order the user actually
clicks through.
"""
import csv
import json
import os

RAW_DIR = os.path.join(os.path.dirname(__file__), '..', '..', '_raw_db_backup_2026-07-23')
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'outbound')


def read_csv(name):
    path = os.path.join(RAW_DIR, name)
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def to_float(v, default=0.0):
    try:
        return float(v) if v not in (None, '') else default
    except (TypeError, ValueError):
        return default


def main():
    orders_raw = read_csv('outbound_orders.csv')
    lines_raw = read_csv('outbound_order_lines.csv')

    # ── outbound_orders.json ────────────────────────────────────────────────
    lines_by_order = {}
    for l in lines_raw:
        lines_by_order.setdefault(l['order_id'], []).append(l)
    # Preserve insertion (id) order within each order, matching "ORDER BY id"
    for oid in lines_by_order:
        lines_by_order[oid].sort(key=lambda r: int(r['id']))

    orders = []
    lines_out = {}
    for o in orders_raw:
        oid = o['id']
        order_lines = lines_by_order.get(oid, [])
        orders.append({
            'id': int(oid),
            'qbo_invoice_id': o['qbo_invoice_id'] or None,
            'invoice_number': o['invoice_number'] or None,
            'customer_name': o['customer_name'] or None,
            'order_date': o['order_date'] or None,
            'daily_order_number': int(o['daily_order_number']) if o['daily_order_number'] else None,
            'status': o['status'] or 'approved',
            'ship_method': o['ship_method'] or None,
            'sales_rep': o['sales_rep'] or None,
            'custom_shipping': o['custom_shipping'] or None,
            'tracking_number': o['tracking_number'] or None,
            'ship_date': o['ship_date'] or None,
            'ship_addr': o['ship_addr'] or None,
            'ship_to_name': o['ship_to_name'] or None,
            'po_number': o['po_number'] or None,
            'line_count': len(order_lines),
        })
        lines_out[oid] = [{
            'line_num': l['line_num'] or '',
            'ref_ea': l['ref_ea'] or '',
            'description': l['description'] or '',
            'qty_ordered': to_float(l['qty_ordered']),
            'wh_location': l['wh_location'] or '',
        } for l in order_lines]

    orders.sort(key=lambda o: (o['order_date'] or '', o['daily_order_number'] or 0))

    demo_order_id = 10  # Unity Physicians Hospital, invoice 41488 -- see module docstring

    orders_payload = {
        'generated_note': 'Full snapshot -- 15 real outbound orders / 17 real order lines, 2026-07-23.',
        'demo_order_id': demo_order_id,
        'orders': orders,
        'lines': lines_out,
    }

    with open(os.path.join(OUT_DIR, 'orders.json'), 'w', encoding='utf-8') as f:
        json.dump(orders_payload, f, indent=1)

    # ── invoices.json (Invoice Approver) ────────────────────────────────────
    products = {p['id']: p for p in read_csv('products.csv')}
    qbo_invoices = read_csv('qbo_invoices.csv')

    # sales_history rows with rate>0, grouped by qbo_invoice_id -- mirrors the
    # true_low_violations / approval_only_violations correlated subqueries.
    sh_by_invoice = {}
    for r in read_csv('sales_history.csv'):
        rate = to_float(r['rate'])
        if rate <= 0:
            continue
        sh_by_invoice.setdefault(r['qbo_invoice_id'], []).append(r)

    invoices = []
    for inv in qbo_invoices:
        qid = inv['qbo_invoice_id']
        true_low_violations = 0
        approval_only_violations = 0
        for sh in sh_by_invoice.get(qid, []):
            p = products.get(sh['product_id'])
            if not p:
                continue
            rate = to_float(sh['rate'])
            true_low = to_float(p['true_low'], None) if p['true_low'] else None
            approval_only = to_float(p['approval_only'], None) if p['approval_only'] else None
            if true_low is not None and rate < true_low:
                true_low_violations += 1
            elif approval_only is not None and rate < approval_only and (
                true_low is None or rate >= true_low
            ):
                approval_only_violations += 1

        invoices.append({
            'qbo_invoice_id': qid,
            'invoice_number': inv['invoice_number'] or None,
            'customer_name': inv['customer_name'] or None,
            'invoice_date': inv['invoice_date'] or None,
            'ship_method': inv['ship_method'] or None,
            'sales_rep': inv['sales_rep'] or None,
            'total_amount': to_float(inv['total_amount']),
            'line_count': int(inv['line_count']) if inv['line_count'] else 0,
            'approval_status': inv['approval_status'] or 'pending',
            'denial_reason': inv['denial_reason'] or None,
            'true_low_violations': true_low_violations,
            'approval_only_violations': approval_only_violations,
        })

    # ORDER BY invoice_date DESC, invoice_number DESC NULLS LAST
    def inv_sort_key(inv):
        num = inv['invoice_number']
        try:
            num_key = int(num)
        except (TypeError, ValueError):
            num_key = -1
        return (inv['invoice_date'] or '', num_key)

    invoices.sort(key=inv_sort_key, reverse=True)

    invoices_payload = {
        'generated_note': (
            'Full snapshot -- all 2,506 QBO-synced invoices, 2026-07-23. '
            'True Low / Approval Only floors were unset for every product in '
            'this snapshot, so pricing-alert badges are computed live from '
            'the data but never populated (matches source data, not a demo shortcut).'
        ),
        'reference_today': '2026-07-23',
        'invoices': invoices,
    }

    with open(os.path.join(OUT_DIR, 'invoices.json'), 'w', encoding='utf-8') as f:
        json.dump(invoices_payload, f, separators=(',', ':'))

    print(f"orders.json: {len(orders)} orders, {sum(len(v) for v in lines_out.values())} lines")
    print(f"invoices.json: {len(invoices)} invoices")


if __name__ == '__main__':
    main()
