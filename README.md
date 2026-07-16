# Portfolio piece — Manifest (Operations Intelligence Platform)

A de-identified portfolio case study built from a real production system.
No company names, branding, credentials, or real data are included anywhere
in this folder — this is a self-contained, isolated copy for a personal
portfolio site and does not touch the actual SurgiCentral codebase.

## What's here

| Path | What it is |
|---|---|
| `case-study.html` | The main write-up: problem, architecture, modules, the analytics engine, and outcomes. Static HTML/CSS/JS, no build step. |
| `demo/index.html` | A working interactive dashboard on synthetic sample data — filters, sortable table, sparklines, item detail drawer. Static, no backend. |
| `code-samples/risk_classifier.py` | A cleaned, generalized excerpt of the core risk-classification logic, with its own README. |

## Deploying to GoDaddy (or any static host)

Everything is plain HTML/CSS/JS — there's no server, database, or build
process required.

1. Upload this folder's contents to your hosting (e.g. via GoDaddy's File
   Manager or FTP), keeping `case-study.html` and the `demo/` folder in the
   same relative location to each other.
2. If you want the case study to be your site's landing page, rename
   `case-study.html` to `index.html` (or point your existing homepage to it).
3. `code-samples/` is reference material for anyone who clicks through from
   the write-up — it doesn't need to be hosted if you'd rather link to it
   from GitHub instead.

## If you want to swap in real screenshots later

The demo dashboard already *is* the "screenshot" — it's live and
clickable rather than a static image, which tends to read better in a
portfolio. If you'd prefer static images instead, the dashboard is a good
thing to screenshot directly (open `demo/index.html` in a browser, resize
to taste).
