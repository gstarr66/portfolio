# SurgiCentral Static Demo — Build Conventions

Read this fully before building any module. Every module-building agent
must follow these so the ~50 pages feel like one coherent site instead of
five unrelated ones.

## What this project is

A static (no server, no DB) clone of the real SurgiCentral Flask app, for
Gary Starr to show in job interviews after losing access to the original
server. Real branding, real data (a snapshot taken 2026-07-23), private/
unlisted distribution (password-gated via `.htaccess`, see
`README_HOSTING.txt`) — not a public marketing site. Fidelity to the real
app's look, data, and business logic matters more than polish-for-its-own-
sake.

## Source material

- **Real templates**: `../surgicentral/templates/<module>/*.html` — the
  actual Jinja templates. Use these as the visual/structural ground truth
  (Bootstrap 5, same card/table layout, same badges/colors). Strip Jinja
  control flow and auth checks; the demo user is always "logged in" with
  every permission.
- **Real business logic**: `../surgicentral/<module>/routes.py` — the
  actual SQL queries and Python that shape what each page displays (joins,
  filters, sort order, computed fields like risk/bucket colors, days-to-
  expiration, etc). Reproduce this logic in your data-extraction script so
  the static JSON matches what the live page would actually show — don't
  invent simplified logic.
- **Real data**: `../_raw_db_backup_2026-07-23/*.csv` — every table, full
  rows, CSV with header, dumped directly from the live Postgres on
  2026-07-23. `../_raw_db_backup_2026-07-23/_schema.json` has column
  names/types for every table if a CSV's dtypes are ambiguous.
  - **Never copy files from that folder into `Clone/`.** It contains rows
    (`qbo_tokens`, `qbo_auth_states`) with live OAuth tokens that must
    never end up in a published static site. Only pull the specific
    columns/rows a real template actually displays.
  - Some tables are large (`inbound_scans` ~193k rows, `outbound_scans`
    ~206k, `competitor_price_history` ~246k, `sku_daily_snapshots` ~131k).
    If a real page has no natural pagination/filter, cap what you embed
    at a few thousand rows max (pick the most representative slice — most
    recent, highest velocity/revenue, non-zero stock, whatever the page's
    own sort order implies) and add a small caption like "showing top 2,000
    of 11,828 for demo performance." Never silently truncate without saying so.

## File/folder convention

- One page = one file, always exactly **one folder below the Clone root**:
  `Clone/<module>/<page>.html` (e.g. `Clone/procurement/index.html`,
  `Clone/inventory/summary.html`). Do not nest deeper — the shared
  prefix logic in `assets/js/site.js` assumes depth 1.
- Data for a module's pages goes in `Clone/data/<module>/<page>.json`.
- Any one-off Python/pandas extraction script you write to produce that
  JSON can live in `Clone/_build_scripts/<module>_extract.py` — fine to
  leave in the repo, it only reads local CSVs and holds no secrets.

## Standard page skeleton

Every page's `<head>` and body wrapper should look like this (adjust
`<title>` and add page-specific `<link>`/`<script>` tags as needed):

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Page Name — SurgiCentral</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="../assets/css/site.css" rel="stylesheet">
</head>
<body>

<div id="nav-placeholder"></div>

<div class="container-fluid px-4">
  <!-- page content here -->
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script src="../assets/js/site.js"></script>
<script>
  // fetch('../data/<module>/<page>.json').then(r => r.json()).then(renderPage);
</script>
</body>
</html>
```

`site.js` auto-injects the real nav into `#nav-placeholder` and rewrites
its `{{PREFIX}}` tokens to `../` (since every page is at depth 1) — you
don't need to build nav markup yourself.

## Data loading pattern

Fetch your page's JSON at load and render it into tables/cards with plain
JS (template literals are fine — no build step, no framework). Keep
sorting/filtering that the real page supports (tabs, search box, zone
filter, etc.) as client-side JS over the already-fetched JSON — don't
require a server round-trip for anything.

## "Fake-live" signature flows (demoStore)

`window.demoStore` (in `site.js`) is a tiny localStorage wrapper:
`get(ns, fallback)`, `set(ns, value)`, `append(ns, row)`, `reset(ns)`.
Use it **only** for these signature flows — everything else that would
normally write to the DB should instead be visually present but inert
(add `data-demo-inert="Short Label"` to the button/link; `site.js` wires
a toast explaining it's not connected in this demo — call
`window.wireInertLinks()` again if you inject such buttons after initial
page load):

| Module | Fake-live flow | Everything else in that module |
|---|---|---|
| Procurement | — (read-only dashboard is the point) | `run-now`, `download` → inert |
| Acquisitions | "New buyback case" form → appends to list | edits → inert |
| Warehouse | Inbound scan (scan_start/scan_live) → appends a scanned row, live-updating count | — |
| QC | Batch review (approve/reject a line item) → updates status in place | locations/notes CRUD → inert |
| Suppliers | Add a communication log entry → appends to timeline | new/edit supplier form → inert |
| Outbound | Pack → Ship flow on one order → advances its status | invoice approver actions → inert |
| Inventory | Submit a hold request → appends to holds list (stays "pending") | approve/release, cycle count, zone moves → inert |

A fake-live action should never claim permanence — after appending, show
a small "Demo — not saved to a server" note near the success toast.

## Data sensitivity

Real customer names, supplier names, pricing, and financials are approved
for use as-is (Gary's call, given this is private/unlisted). Do **not**
include: `qbo_tokens`, `qbo_auth_states` (live OAuth secrets), or anything
from `docker-compose.yml`/`config.py` (API keys, DB password, SMTP
password, Mongo URI). None of that is displayed by any real template
anyway, so this shouldn't require leaving anything out that the live app
actually shows.

## Cross-module links

Link to other modules using the nav conventions above (`../<module>/<page>.html`).
If a real template links somewhere out of scope (e.g. a QBO invoice
detail that only exists server-side), make it `data-demo-inert`.
