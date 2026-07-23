"""Webhook service tests: auth fail-closed, HMAC, risk-layer routing.

The IBKR broker is replaced with a stub; no network or Gateway needed.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from paper_trading_boto import webhook_service
from paper_trading_boto.config import Settings

SECRET = "test-secret"


class StubBroker:
    def __init__(self):
        self.submitted = []

    def connect(self):
        pass

    def disconnect(self):
        pass

    def current_price(self, symbol):
        return 100.0

    def positions(self):
        return {}

    def equity(self):
        return 100_000.0

    def submit_order(self, order):
        self.submitted.append(order)
        return "ib-42"


@pytest.fixture
def client(monkeypatch):
    stub = StubBroker()
    monkeypatch.setattr(
        webhook_service, "settings",
        Settings(tradingview_secret=SECRET, risk_fraction=0.05),
    )
    monkeypatch.setattr(webhook_service, "_make_broker", lambda: stub)
    test_client = TestClient(webhook_service.app)
    test_client.stub = stub
    return test_client


def signed(payload: dict) -> tuple[bytes, dict]:
    body = json.dumps(payload).encode()
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Signature": signature, "Content-Type": "application/json"}


def test_missing_auth_is_rejected(client):
    response = client.post("/webhook", json={"symbol": "AAPL", "action": "BUY"})
    assert response.status_code == 401
    assert client.stub.submitted == []


def test_wrong_signature_is_rejected(client):
    body = json.dumps({"symbol": "AAPL", "action": "BUY"}).encode()
    response = client.post("/webhook", content=body,
                           headers={"X-Signature": "0" * 64,
                                    "Content-Type": "application/json"})
    assert response.status_code == 401


def test_wrong_inbody_secret_is_rejected(client):
    response = client.post("/webhook",
                           json={"symbol": "AAPL", "action": "BUY", "secret": "nope"})
    assert response.status_code == 401


def test_unset_secret_fails_closed(client, monkeypatch):
    """Regression: original service skipped auth entirely when the env var
    was missing. Now it must refuse service, not accept everything."""
    monkeypatch.setattr(webhook_service, "settings",
                        Settings(tradingview_secret=None))
    response = client.post("/webhook", json={"symbol": "AAPL", "action": "BUY"})
    assert response.status_code == 503


def test_valid_hmac_places_risk_sized_order(client):
    body, headers = signed({"symbol": "AAPL", "action": "BUY"})
    response = client.post("/webhook", content=body, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["order_id"] == "ib-42"
    # Sized by risk layer (5% of 100k at $100 = 50), not payload-controlled.
    assert data["quantity"] == 50
    order = client.stub.submitted[0]
    assert order.stop_loss_price == pytest.approx(95.0)


def test_inbody_secret_still_works(client):
    response = client.post("/webhook",
                           json={"symbol": "AAPL", "action": "BUY", "secret": SECRET})
    assert response.status_code == 200


def test_sell_without_position_is_rejected_by_risk(client):
    body, headers = signed({"symbol": "AAPL", "action": "SELL"})
    response = client.post("/webhook", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert client.stub.submitted == []


def test_bad_payload_is_400(client):
    body, headers = signed({"symbol": "AAPL", "action": "HOLD"})
    assert client.post("/webhook", content=body, headers=headers).status_code == 400
    body, headers = signed({"action": "BUY"})
    assert client.post("/webhook", content=body, headers=headers).status_code == 400
