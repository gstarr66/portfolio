"""
Extraction script for the Shipments module — reproduces
../../surgicentral/shipments/routes.py against
../../_raw_db_backup_2026-07-23/incoming_shipments.csv (only 2 rows in
this snapshot — embedded in full).

Run: python shipments_extract.py   (from Clone/_build_scripts/)

Outputs:
    Clone/data/shipments/index.json
"""
import csv
import json
import os

RAW = os.path.join(os.path.dirname(__file__), '..', '..', '_raw_db_backup_2026-07-23')
OUT = os.path.join(os.path.dirname(__file__), '..', 'data', 'shipments')
os.makedirs(OUT, exist_ok=True)

STATUSES = ['Pending', 'Received', 'Awaiting More Boxes']


def main():
    shipments = []
    with open(os.path.join(RAW, 'incoming_shipments.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            shipments.append({
                'id': int(row['id']),
                'vendor': row['vendor'] or None,
                'po_number': row['po_number'] or None,
                'received_date': row['received_date'] or None,
                'received_time': row['received_time'] or None,
                'status': row['status'] or 'Pending',
                'total_boxes': int(row['total_boxes']) if row['total_boxes'] else None,
                'notes': row['notes'] or None,
            })

    # Real route sorts by received_date DESC, received_time DESC NULLS LAST, id DESC
    shipments.sort(key=lambda s: (s['received_date'] or '', s['received_time'] or '', s['id']),
                    reverse=True)

    with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'shipments': shipments, 'statuses': STATUSES}, f, indent=2)

    print(f"index.json: {len(shipments)} shipments")


if __name__ == '__main__':
    main()
