"""Razorpay Settlements API loader — an alternative to load_settlements()
(CSV) that maps into the exact same Settlement dataclass, so
run_reconciliation() never needs to know which source produced its input.

Verified against the real API without credentials (see docs/ADR-002):
    GET https://api.razorpay.com/v1/settlements -> 401
    {"error": {"code": "BAD_REQUEST_ERROR", "description": "..."}}
RazorpayAPIError's message-building below is built against that real,
observed error envelope, not a guessed one.
"""

from decimal import Decimal
from datetime import date

import httpx

from reconcile import Settlement

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"
PAGE_SIZE = 100


class RazorpayAPIError(Exception):
    """Raised for a non-200 Razorpay response."""


def _raise_for_response(resp):
    if resp.status_code == 200:
        return
    try:
        description = resp.json()["error"]["description"]
    except Exception:
        description = resp.text
    raise RazorpayAPIError(f"Razorpay API returned {resp.status_code}: {description}")


def fetch_settlements_page(key_id, key_secret, count=PAGE_SIZE, skip=0,
                            from_ts=None, to_ts=None, http_get=httpx.get):
    """One page of GET /v1/settlements. http_get is injectable — mirrors
    llm_fn in run_reconciliation() — so tests never make a real network
    call and never need real credentials."""
    params = {"count": count, "skip": skip}
    if from_ts is not None:
        params["from"] = from_ts
    if to_ts is not None:
        params["to"] = to_ts
    resp = http_get(
        f"{RAZORPAY_BASE_URL}/settlements",
        params=params,
        auth=(key_id, key_secret),
        timeout=10,
    )
    _raise_for_response(resp)
    return resp.json()


def _to_settlement(item):
    utr = item.get("utr")
    return Settlement(
        settlement_id=item["id"],
        reference_id=utr if utr else item["id"],
        amount=Decimal(item["amount"]) / Decimal(100),
        date=date.fromtimestamp(item["created_at"]),
        status=item["status"],
    )


def load_settlements_from_razorpay(key_id, key_secret, from_ts=None, to_ts=None,
                                    http_get=httpx.get):
    """Paginates fetch_settlements_page (count=PAGE_SIZE per page, via
    `skip`) until a short page ends the collection. Returns
    list[Settlement] — the exact same dataclass load_settlements() (CSV)
    returns, so the matching engine itself never changes."""
    items = []
    skip = 0
    while True:
        page = fetch_settlements_page(
            key_id, key_secret, count=PAGE_SIZE, skip=skip,
            from_ts=from_ts, to_ts=to_ts, http_get=http_get,
        )
        page_items = page["items"]
        items.extend(page_items)
        if len(page_items) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return [_to_settlement(item) for item in items]
