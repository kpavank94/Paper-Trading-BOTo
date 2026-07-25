"""Tests for the Alpaca news tool and market-data loader (mocked HTTP, no key)."""

from __future__ import annotations

import json

import pandas as pd
import pytest


# --------------------------------------------------------------------------- #
# News tool
# --------------------------------------------------------------------------- #

def _reset(monkeypatch, **env):
    import src.config.accessor as acc

    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    acc.reset_env_config()


def test_news_unavailable_without_key(monkeypatch):
    from src.tools.alpaca_news_tool import AlpacaNewsTool

    _reset(monkeypatch, APCA_API_KEY_ID=None, APCA_API_SECRET_KEY=None)
    assert AlpacaNewsTool.check_available() is False


def test_news_available_with_key(monkeypatch):
    from src.tools.alpaca_news_tool import AlpacaNewsTool

    _reset(monkeypatch, APCA_API_KEY_ID="k", APCA_API_SECRET_KEY="s")
    assert AlpacaNewsTool.check_available() is True


def test_sentiment_lexicon():
    from src.tools.alpaca_news_tool import _tag_sentiment

    assert _tag_sentiment("Company beats estimates, shares surge") == "positive"
    assert _tag_sentiment("Stock plunges on earnings miss and probe") == "negative"
    assert _tag_sentiment("Company holds annual meeting") == "neutral"


def test_news_execute_parses_articles(monkeypatch):
    from src.tools import alpaca_news_tool as mod

    _reset(monkeypatch, APCA_API_KEY_ID="k", APCA_API_SECRET_KEY="s")

    fake = {
        "news": [
            {
                "headline": "NVDA surges to record on strong demand",
                "summary": "Revenue beats.",
                "source": "benzinga",
                "url": "https://example.com/a",
                "symbols": ["NVDA"],
                "created_at": "2026-07-25T12:00:00Z",
            }
        ]
    }

    class _Resp:
        def read(self):
            return json.dumps(fake).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import urllib.request as _ur

    monkeypatch.setattr(_ur, "urlopen", lambda *a, **k: _Resp())
    out = json.loads(mod.AlpacaNewsTool().execute(symbols="NVDA", limit=5))
    assert out["ok"] is True
    assert out["count"] == 1
    art = out["articles"][0]
    assert art["symbols"] == ["NVDA"]
    assert art["sentiment"] == "positive"
    assert art["published"] == "2026-07-25T12:00:00Z"


# --------------------------------------------------------------------------- #
# Data loader
# --------------------------------------------------------------------------- #

def test_loader_registered():
    from backtest.loaders.registry import VALID_SOURCES, _ensure_registered, LOADER_REGISTRY

    _ensure_registered()
    assert "alpaca" in VALID_SOURCES
    assert "alpaca" in LOADER_REGISTRY


def test_loader_unavailable_without_key(monkeypatch):
    from backtest.loaders.alpaca_loader import DataLoader

    _reset(monkeypatch, APCA_API_KEY_ID=None, APCA_API_SECRET_KEY=None)
    assert DataLoader().is_available() is False


def test_loader_fetch_normalizes_bars(monkeypatch):
    from backtest.loaders import alpaca_loader as mod

    _reset(monkeypatch, APCA_API_KEY_ID="k", APCA_API_SECRET_KEY="s", VIBE_TRADING_DATA_CACHE="0")

    payload = {
        "bars": [
            {"t": "2024-01-02T05:00:00Z", "o": 10.0, "h": 11.0, "l": 9.5, "c": 10.5, "v": 1000},
            {"t": "2024-01-03T05:00:00Z", "o": 10.5, "h": 12.0, "l": 10.0, "c": 11.5, "v": 2000},
        ],
        "next_page_token": None,
    }
    monkeypatch.setattr(mod, "throttled_get_json", lambda *a, **k: payload)

    out = mod.DataLoader().fetch(["AAPL.US"], "2024-01-01", "2024-01-31")
    assert "AAPL.US" in out
    df = out["AAPL.US"]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 2
    assert isinstance(df.index, pd.DatetimeIndex)
    assert df["close"].iloc[-1] == 11.5
