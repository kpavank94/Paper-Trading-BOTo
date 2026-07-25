"""Tests for the advisory TradingView webhook receiver (src/api/webhook_routes)."""

from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient with the webhook routes mounted and an isolated signals file."""
    monkeypatch.setenv("TRADINGVIEW_SIGNALS_PATH", str(tmp_path / "signals.jsonl"))
    import src.config.accessor as acc

    acc.reset_env_config()
    wr = importlib.import_module("src.api.webhook_routes")
    app = FastAPI()
    wr.register_webhook_routes(app, require_auth=lambda: None)
    acc.reset_env_config()
    return TestClient(app)


def _set_secret(monkeypatch, value: str | None) -> None:
    import src.config.accessor as acc

    if value is None:
        monkeypatch.delenv("TRADINGVIEW_WEBHOOK_SECRET", raising=False)
    else:
        monkeypatch.setenv("TRADINGVIEW_WEBHOOK_SECRET", value)
    acc.reset_env_config()


def test_fail_closed_when_secret_unset(client, monkeypatch):
    _set_secret(monkeypatch, None)
    r = client.post("/webhook/tradingview", json={"symbol": "AAPL", "action": "BUY"})
    assert r.status_code == 503


def test_wrong_secret_rejected(client, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    r = client.post("/webhook/tradingview", json={"secret": "nope", "symbol": "AAPL", "action": "BUY"})
    assert r.status_code == 401


def test_valid_signal_recorded_advisory(client, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    r = client.post(
        "/webhook/tradingview",
        json={"secret": "s3cret", "symbol": "NVDA", "action": "BUY", "quantity": 10},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "recorded"
    assert body["advisory"] is True
    assert body["signal"]["symbol"] == "NVDA"
    # the secret must never be echoed back inside the stored raw payload
    assert "secret" not in body["signal"]["raw"]


def test_secret_via_header(client, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    r = client.post(
        "/webhook/tradingview",
        json={"symbol": "TSLA", "action": "SELL"},
        headers={"X-Webhook-Secret": "s3cret"},
    )
    assert r.status_code == 200


def test_invalid_action_rejected(client, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    r = client.post(
        "/webhook/tradingview",
        json={"secret": "s3cret", "symbol": "AAPL", "action": "HODL"},
    )
    assert r.status_code == 400


def test_readback_returns_recorded_signals(client, monkeypatch):
    _set_secret(monkeypatch, "s3cret")
    client.post("/webhook/tradingview", json={"secret": "s3cret", "symbol": "AAA", "action": "BUY"})
    client.post("/webhook/tradingview", json={"secret": "s3cret", "symbol": "BBB", "action": "SELL"})
    r = client.get("/webhook/tradingview/signals?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    # newest first
    assert body["signals"][0]["symbol"] == "BBB"
