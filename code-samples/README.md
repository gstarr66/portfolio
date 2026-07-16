# Code sample — risk classification engine

`risk_classifier.py` is a generalized excerpt from the procurement module of
a production Flask/PostgreSQL operations platform. It's the piece of the
system responsible for turning raw inventory numbers into a single,
priority-ordered risk label per SKU.

Company data, thresholds, and naming have been altered from the original.
The structure — a strict, top-to-bottom priority order where the first
matching condition wins — is representative of the real implementation.

## Why priority order matters

Inventory risk conditions overlap. A SKU can simultaneously have zero stock,
low margin tier, and an expiring lot. Scoring each condition independently
and picking the "worst" by some weighted formula is fragile and hard to
reason about. Instead, the real system asks a fixed sequence of yes/no
questions and stops at the first "yes" — so the ranking is deterministic,
auditable, and easy to explain to a non-technical stakeholder ("we always
treat a stockout on a top-tier item as more urgent than a slow-moving
overstock, full stop").

## Where this sits in the larger system

In production, this function runs against every SKU on a scheduled sync
from the source-of-truth database, and its output drives:

- the operations dashboard's risk table and alert counts (see `../demo`)
- a daily reorder recommendation list, ranked by `reorder_score`
- the "at-risk units" and "dead capital" summary figures shown to ops leadership

Run it directly with:

```
python risk_classifier.py
```
