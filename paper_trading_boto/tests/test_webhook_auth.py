"""The webhook must never place an order without a valid pre-shared secret.

ib_insync is stubbed so this runs offline; the point under test is the auth
gate, not the broker.
"""

from __future__ import annotations

import sys
import types

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


def _load_service(monkeypatch, secret):
    """Import the webhook service with ib_insync stubbed and a recording broker."""
    stub = types.ModuleType("ib_insync")
    for attr in ("IB", "Stock", "MarketOrder", "LimitOrder", "util", "Contract"):
        setattr(stub, attr, object)
    monkeypatch.setitem(sys.modules, "ib_insync", stub)
    sys.modules.pop("paper_trading_boto.tradingview_service", None)
    sys.modules.pop("paper_trading_boto.ibkr_interface", None)

    import paper_trading_boto.tradingview_service as svc

    placed = []

    class _FakeInterface:
        def connect(self):
            pass

        def disconnect(self):
            pass

        def place_market_order(self, symbol, quantity, action):
            placed.append((symbol, quantity, action))
            return "oid-1"

    monkeypatch.setattr(svc, "get_ibkr_interface", lambda: _FakeInterface())
    monkeypatch.setattr(svc, "TRADINGVIEW_SECRET", secret)
    return svc, placed


def test_unset_secret_refuses_orders(monkeypatch):
    svc, placed = _load_service(monkeypatch, secret=None)  # the shipped default
    client = TestClient(svc.app)
    resp = client.post("/webhook", json={"symbol": "AAPL", "action": "BUY", "quantity": 10000})
    assert resp.status_code == 503
    assert placed == []


def test_missing_or_wrong_secret_is_rejected(monkeypatch):
    svc, placed = _load_service(monkeypatch, secret="letmein")
    client = TestClient(svc.app)

    no_secret = client.post("/webhook", json={"symbol": "AAPL", "action": "BUY"})
    assert no_secret.status_code == 401

    wrong = client.post(
        "/webhook", json={"secret": "nope", "symbol": "AAPL", "action": "BUY"}
    )
    assert wrong.status_code == 401
    assert placed == []


def test_correct_secret_places_order(monkeypatch):
    svc, placed = _load_service(monkeypatch, secret="letmein")
    client = TestClient(svc.app)
    resp = client.post(
        "/webhook",
        json={"secret": "letmein", "symbol": "AAPL", "action": "BUY", "quantity": 5},
    )
    assert resp.status_code == 200
    assert placed == [("AAPL", 5, "BUY")]
