"""
Priority-ordered inventory risk classification.

Generalized excerpt from a production procurement module. Domain names,
company data, and thresholds have been altered from the original; the
structure of the ranking logic is representative of the real system.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Sku:
    sku: str
    tier: str                      # "A" | "B" | "C" | "D", margin/importance tier
    on_hand: int
    velocity_6mo: float             # units sold per month, trailing 6 months
    velocity_3mo: float              # units sold per month, trailing 3 months
    months_of_stock: float
    days_to_expiration: Optional[int] = None   # None if not lot/expiration tracked


# Evaluated top to bottom; the first matching condition wins. This ordering
# is deliberate: a zero-stock item is always a stockout regardless of its
# margin tier, and an expiring lot always outranks a routine low-stock flag.
def classify_risk(sku: Sku) -> str:
    if sku.on_hand == 0:
        if sku.tier == "A" and sku.velocity_6mo > 5:
            return "STOCKOUT — BUY IMMEDIATELY"
        if sku.tier in ("A", "B"):
            return "STOCKOUT — HIGH PRIORITY"
        if sku.velocity_6mo > 5:
            return "STOCKOUT — REORDER NOW"
        if sku.velocity_6mo == 0:
            return "DEAD STOCK — NO DEMAND"
        return "STOCKOUT"

    if sku.days_to_expiration is not None:
        if sku.days_to_expiration <= 30:
            return "AGING — CRITICAL"
        if sku.days_to_expiration <= 90:
            return "AGING — URGENT"
        if sku.days_to_expiration <= 180:
            return "AGING — WATCH"

    if sku.tier in ("A", "B") and sku.months_of_stock <= 3:
        return "LOW STOCK — PRIORITY ITEM"
    if sku.months_of_stock > 12:
        return "OVERSTOCKED"

    return "OK"


def reorder_score(sku: Sku) -> float:
    """
    Ranks stockout-risk SKUs for a buy list. Blends the 6-month baseline
    velocity with the 3-month trend so an item that is accelerating floats
    above one that is merely fast-moving on average.
    """
    trend_factor = 1.0
    if sku.velocity_6mo > 0:
        trend_factor = 1 + max(-0.5, min(1.0, (sku.velocity_3mo - sku.velocity_6mo) / sku.velocity_6mo))
    tier_weight = {"A": 4, "B": 3, "C": 2, "D": 1}[sku.tier]
    return sku.velocity_6mo * trend_factor * tier_weight


if __name__ == "__main__":
    sample = [
        Sku("SK-10001-A", tier="A", on_hand=0, velocity_6mo=8.0, velocity_3mo=11.0, months_of_stock=0),
        Sku("SK-10002-B", tier="C", on_hand=40, velocity_6mo=2.0, velocity_3mo=1.5, months_of_stock=20),
        Sku("SK-10003-C", tier="B", on_hand=12, velocity_6mo=6.0, velocity_3mo=6.5, months_of_stock=2, days_to_expiration=45),
    ]
    for s in sorted(sample, key=reorder_score, reverse=True):
        print(f"{s.sku:14s} {classify_risk(s):28s} score={reorder_score(s):.1f}")
