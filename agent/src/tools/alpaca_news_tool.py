"""Alpaca news tool: recent US-market news headlines via the Alpaca News API.

Wraps Alpaca's ``/v1beta1/news`` endpoint behind the BaseTool contract. Free
with a paper account (no separate market-data subscription needed for news).
Credentials come from ``APCA_API_KEY_ID`` / ``APCA_API_SECRET_KEY``; the tool
advertises itself as unavailable when they are unset, so the agent never calls a
tool that must fail. Returns a flat ``{headline, summary, source, url, symbols,
published}`` shape, mirroring ``get_stock_news`` so the two are interchangeable.

Alpaca does not return a numeric sentiment score; a lightweight lexicon tag
(positive / negative / neutral) is derived from the headline so downstream
prompts get a coarse directional hint without implying false precision.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.tools import BaseTool
from src.config.accessor import get_env_config
from src.security.scanner import with_security_warnings

logger = logging.getLogger(__name__)

_NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
_DEFAULT_LIMIT = 20
_TIMEOUT_S = 15

# Coarse headline lexicon — a directional hint, not a calibrated score.
_POS = ("beat", "surge", "soar", "jump", "rally", "record", "upgrade", "raises",
        "growth", "profit", "gains", "tops", "outperform", "bullish", "wins")
_NEG = ("miss", "plunge", "sink", "fall", "drop", "cut", "downgrade", "lawsuit",
        "probe", "loss", "slump", "warns", "recall", "bearish", "halts", "fraud")


def _tag_sentiment(text: str) -> str:
    """Return 'positive' / 'negative' / 'neutral' from a headline (lexicon only)."""
    low = text.lower()
    pos = sum(w in low for w in _POS)
    neg = sum(w in low for w in _NEG)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


class AlpacaNewsTool(BaseTool):
    """Recent US-market news headlines from Alpaca, with a coarse sentiment tag."""

    name = "get_alpaca_news"

    @classmethod
    def check_available(cls) -> bool:
        """Available only when Alpaca data credentials are configured."""
        cfg = get_env_config().data
        return bool(cfg.apca_api_key_id.strip() and cfg.apca_api_secret_key.strip())

    description = (
        "Fetch recent US-market news headlines from Alpaca (real-time, free with a "
        "paper account). Optionally filter by one or more symbols. Each article has "
        "headline, summary, source, url, symbols, published time, and a coarse "
        "sentiment tag (positive/negative/neutral) derived from the headline. "
        'Example: {"symbols": "AAPL,NVDA", "limit": 10}.'
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbols": {
                "type": "string",
                "description": (
                    "Comma-separated US tickers to filter by, e.g. 'AAPL,NVDA'. "
                    "Omit for the broad market news feed."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of articles to return (1-50). Default 20.",
                "default": _DEFAULT_LIMIT,
            },
        },
        "required": [],
    }
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        """Fetch Alpaca news and return a JSON envelope.

        Args:
            **kwargs: optional ``symbols`` (comma-separated) and ``limit`` (1-50).

        Returns:
            JSON string: ``{"ok": true, "source": "alpaca", "articles": [...]}``
            or ``{"ok": false, "error": ...}`` on failure.
        """
        import urllib.parse
        import urllib.request

        cfg = get_env_config().data
        key_id = cfg.apca_api_key_id.strip()
        secret = cfg.apca_api_secret_key.strip()
        if not (key_id and secret):
            return json.dumps(
                {"ok": False, "error": "Alpaca credentials not set (APCA_API_KEY_ID / APCA_API_SECRET_KEY)."},
                ensure_ascii=False,
            )

        limit = max(1, min(int(kwargs.get("limit", _DEFAULT_LIMIT)), 50))
        params: dict[str, Any] = {"limit": limit, "sort": "desc"}
        symbols = (kwargs.get("symbols") or "").strip()
        if symbols:
            params["symbols"] = symbols

        url = _NEWS_URL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(
            url,
            headers={
                "APCA-API-KEY-ID": key_id,
                "APCA-API-SECRET-KEY": secret,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
                data = json.loads(resp.read().decode("utf-8", "ignore"))
        except Exception as exc:  # noqa: BLE001 — surface a clean error to the agent
            logger.warning("alpaca news fetch failed: %s", exc)
            return json.dumps({"ok": False, "error": f"Alpaca news request failed: {exc}"}, ensure_ascii=False)

        articles = [_normalize(a) for a in (data.get("news") or [])]
        payload = {"ok": True, "source": "alpaca", "count": len(articles), "articles": articles}
        payload = with_security_warnings(
            payload, fields=("articles.*.headline", "articles.*.summary")
        )
        return json.dumps(payload, ensure_ascii=False)


def _normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Flatten one Alpaca news article to the shared news shape + sentiment tag."""
    headline = raw.get("headline", "") or ""
    summary = raw.get("summary", "") or ""
    return {
        "headline": headline,
        "summary": summary,
        "source": raw.get("source"),
        "url": raw.get("url"),
        "symbols": raw.get("symbols", []),
        "published": raw.get("created_at") or raw.get("updated_at"),
        "sentiment": _tag_sentiment(f"{headline} {summary}"),
    }
