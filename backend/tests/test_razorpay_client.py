from datetime import date
from decimal import Decimal

import pytest

from razorpay_client import (
    RazorpayAPIError,
    fetch_settlements_page,
    load_settlements_from_razorpay,
)


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self):
        return self._body


def fake_http_get_single_page(items):
    def http_get(url, params=None, auth=None, timeout=None):
        return FakeResponse(200, {"entity": "collection", "count": len(items), "items": items})
    return http_get


def make_item(id="setl_1", utr="UTR12345", amount=100000, created_at=1751328000, status="processed"):
    return {"id": id, "utr": utr, "amount": amount, "created_at": created_at, "status": status}


def test_fetch_settlements_page_returns_parsed_json():
    http_get = fake_http_get_single_page([make_item()])
    page = fetch_settlements_page("key", "secret", http_get=http_get)
    assert page["count"] == 1
    assert page["items"][0]["id"] == "setl_1"


def test_fetch_settlements_page_raises_with_razorpay_error_description():
    # Real observed shape from the live API (see docs/ADR-002):
    # {"error": {"code": "BAD_REQUEST_ERROR", "description": "..."}}
    def http_get(url, params=None, auth=None, timeout=None):
        return FakeResponse(401, {"error": {"code": "BAD_REQUEST_ERROR",
                                             "description": "Please provide your api key for authentication purposes"}})

    with pytest.raises(RazorpayAPIError, match="Please provide your api key"):
        fetch_settlements_page("bad-key", "bad-secret", http_get=http_get)


def test_load_settlements_maps_utr_to_reference_id():
    http_get = fake_http_get_single_page([make_item(id="setl_1", utr="UTR999", amount=150050,
                                                      created_at=1751328000, status="processed")])
    settlements = load_settlements_from_razorpay("key", "secret", http_get=http_get)

    assert len(settlements) == 1
    s = settlements[0]
    assert s.settlement_id == "setl_1"
    assert s.reference_id == "UTR999"
    assert s.amount == Decimal("1500.50")
    assert s.date == date.fromtimestamp(1751328000)
    assert s.status == "processed"


def test_load_settlements_falls_back_to_id_when_utr_missing():
    # A settlement not yet bank-settled has no UTR assigned yet — an
    # honest miss on the rule tier, not a fabricated reference.
    http_get = fake_http_get_single_page([make_item(id="setl_2", utr=None, status="created")])
    settlements = load_settlements_from_razorpay("key", "secret", http_get=http_get)

    assert settlements[0].reference_id == "setl_2"


def test_load_settlements_paginates_across_multiple_pages(monkeypatch):
    import razorpay_client
    monkeypatch.setattr(razorpay_client, "PAGE_SIZE", 2)
    all_items = [make_item(id=f"setl_{i}", utr=f"UTR{i}") for i in range(5)]

    def http_get(url, params=None, auth=None, timeout=None):
        skip = params["skip"]
        count = params["count"]
        page_items = all_items[skip:skip + count]
        return FakeResponse(200, {"entity": "collection", "count": len(page_items), "items": page_items})

    settlements = load_settlements_from_razorpay("key", "secret", http_get=http_get)

    assert len(settlements) == 5
    assert [s.settlement_id for s in settlements] == [f"setl_{i}" for i in range(5)]


def test_load_settlements_passes_from_and_to_ts_through_to_the_request():
    captured_params = {}

    def http_get(url, params=None, auth=None, timeout=None):
        captured_params.update(params)
        return FakeResponse(200, {"entity": "collection", "count": 0, "items": []})

    load_settlements_from_razorpay("key", "secret", from_ts=1000, to_ts=2000, http_get=http_get)
    assert captured_params["from"] == 1000
    assert captured_params["to"] == 2000
