"""Tests for the GDELT news + sentiment tool (mocked HTTP; no key, no network)."""

from __future__ import annotations

import json

import pytest


def test_available_without_key():
    from src.tools.gdelt_news_tool import GdeltNewsTool

    # GDELT needs no key/signup — the tool is always available.
    assert GdeltNewsTool.check_available() is True


def test_tone_label_mapping():
    from src.tools.gdelt_news_tool import _label_from_tone

    assert _label_from_tone(2.0) == "positive"
    assert _label_from_tone(-2.0) == "negative"
    assert _label_from_tone(0.1) == "neutral"


def test_query_required():
    from src.tools.gdelt_news_tool import GdeltNewsTool

    out = json.loads(GdeltNewsTool().execute(query="  "))
    assert out["ok"] is False


def test_execute_articles_and_sentiment(monkeypatch):
    from src.tools import gdelt_news_tool as mod

    art = {"articles": [
        {"title": "NVIDIA shares surge to record", "url": "https://x/1",
         "domain": "finance.yahoo.com", "seendate": "20260725T211500Z",
         "sourcecountry": "US", "language": "English"},
    ]}
    tone = {"timeline": [{"series": "Average Tone",
                          "data": [{"date": "t1", "value": 1.0}, {"date": "t2", "value": 2.0}]}]}

    calls = {"n": 0}

    def fake_get_json(url):
        calls["n"] += 1
        return art if "ArtList" in url else tone

    monkeypatch.setattr(mod, "_get_json", fake_get_json)
    out = json.loads(mod.GdeltNewsTool().execute(query="NVIDIA", timespan="3d", max_results=5))

    assert out["ok"] is True
    assert out["source"] == "gdelt"
    assert out["count"] == 1
    assert out["articles"][0]["source_country"] == "US"
    assert out["articles"][0]["sentiment_hint"] == "positive"
    assert out["sentiment"]["label"] == "positive"
    assert out["sentiment"]["mean_tone"] == 1.5
    assert out["sentiment"]["n_points"] == 2


def test_tone_ratelimit_degrades_gracefully(monkeypatch):
    """A 429 on the tone call must not fail the whole request — articles still return."""
    from src.tools import gdelt_news_tool as mod

    art = {"articles": [{"title": "Company plunges on probe", "url": "https://x/2",
                         "domain": "d", "seendate": "t", "sourcecountry": "US", "language": "English"}]}

    def fake_get_json(url):
        if "ArtList" in url:
            return art
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(mod, "_get_json", fake_get_json)
    out = json.loads(mod.GdeltNewsTool().execute(query="ACME"))

    assert out["ok"] is True
    assert out["count"] == 1
    assert out["sentiment"] is None  # tone unavailable, but articles present
    assert out["articles"][0]["sentiment_hint"] == "negative"  # lexicon fallback


def test_artlist_failure_returns_error(monkeypatch):
    from src.tools import gdelt_news_tool as mod

    def fake_get_json(url):
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(mod, "_get_json", fake_get_json)
    out = json.loads(mod.GdeltNewsTool().execute(query="ACME"))
    assert out["ok"] is False
    assert "GDELT" in out["error"]
