"""GDELT news + sentiment tool — global news with tone, no API key, no signup.

Wraps the public GDELT DOC 2.0 API (``api.gdeltproject.org``), which needs no
key or login and works worldwide — the right fit where US-only services (e.g.
Alpaca) can't be used. Two calls per query:

* ``mode=ArtList``     — recent matching articles (title/url/domain/date/…).
* ``mode=TimelineTone``— GDELT's own "Average Tone" series, reduced here to one
  mean-tone number plus a positive/negative/neutral label. GDELT tone runs
  roughly -10 (very negative) to +10 (very positive), 0 ≈ neutral.

GDELT rate-limits aggressively (HTTP 429). The tone call is best-effort: if it
429s or returns nothing, articles are still returned and each carries a coarse
lexicon tag as a fallback sentiment hint.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.tools import BaseTool
from src.security.scanner import with_security_warnings

logger = logging.getLogger(__name__)

_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_DEFAULT_TIMESPAN = "3d"
_DEFAULT_LIMIT = 20
_TIMEOUT_S = 20

_POS = ("beat", "surge", "soar", "jump", "rally", "record", "upgrade", "raises",
        "growth", "profit", "gains", "tops", "outperform", "bullish", "wins")
_NEG = ("miss", "plunge", "sink", "fall", "drop", "cut", "downgrade", "lawsuit",
        "probe", "loss", "slump", "warns", "recall", "bearish", "halts", "fraud")


def _tag(text: str) -> str:
    """Coarse positive/negative/neutral tag from a headline (lexicon only)."""
    low = text.lower()
    p = sum(w in low for w in _POS)
    n = sum(w in low for w in _NEG)
    return "positive" if p > n else "negative" if n > p else "neutral"


def _label_from_tone(mean_tone: float) -> str:
    """Map GDELT mean tone to a positive/negative/neutral label."""
    if mean_tone > 0.5:
        return "positive"
    if mean_tone < -0.5:
        return "negative"
    return "neutral"


def _get_json(url: str) -> Any:
    """GET a GDELT URL and decode JSON; raise on 429/other HTTP errors."""
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": "vibe-trading/gdelt"})
    with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
        raw = resp.read().decode("utf-8", "ignore")
    return json.loads(raw) if raw.strip() else {}


class GdeltNewsTool(BaseTool):
    """Global news headlines + aggregate sentiment via GDELT (no key, worldwide)."""

    name = "get_gdelt_news"
    description = (
        "Fetch recent global news for a company or topic via GDELT (free, no API "
        "key, works worldwide). Returns matching articles (title, url, domain, "
        "published time, source country, language) and an aggregate SENTIMENT read "
        "(GDELT mean 'tone', roughly -10..+10, with a positive/negative/neutral "
        "label). Query with a company or keyword, not a ticker — e.g. 'NVIDIA' or "
        "'Kweichow Moutai'. Example: {\"query\": \"NVIDIA\", \"timespan\": \"3d\"}."
    )
    parameters = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Company name or keyword to search (not a ticker), e.g. 'NVIDIA'.",
            },
            "timespan": {
                "type": "string",
                "description": "Look-back window, e.g. '24h', '3d', '1w', '1m'. Default '3d'.",
                "default": _DEFAULT_TIMESPAN,
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of articles to return (1-50). Default 20.",
                "default": _DEFAULT_LIMIT,
            },
        },
        "required": ["query"],
    }
    repeatable = True

    def execute(self, **kwargs: Any) -> str:
        """Fetch GDELT articles + aggregate tone and return a JSON envelope.

        Args:
            **kwargs: ``query`` (required), optional ``timespan`` and ``max_results``.

        Returns:
            JSON: ``{"ok": true, "source": "gdelt", "query": ..., "sentiment":
            {"mean_tone", "label", "n_points"} | null, "articles": [...]}`` or
            ``{"ok": false, "error": ...}``.
        """
        import urllib.parse

        query = (kwargs.get("query") or "").strip()
        if not query:
            return json.dumps({"ok": False, "error": "query is required"}, ensure_ascii=False)
        timespan = (kwargs.get("timespan") or _DEFAULT_TIMESPAN).strip()
        limit = max(1, min(int(kwargs.get("max_results", _DEFAULT_LIMIT)), 50))

        art_url = _DOC_URL + "?" + urllib.parse.urlencode({
            "query": query, "mode": "ArtList", "maxrecords": limit,
            "format": "json", "sort": "DateDesc", "timespan": timespan,
        })
        try:
            art = _get_json(art_url)
        except Exception as exc:  # noqa: BLE001 — surface a clean error to the agent
            logger.warning("gdelt ArtList failed: %s", exc)
            return json.dumps(
                {"ok": False, "error": f"GDELT article request failed (rate-limited?): {exc}"},
                ensure_ascii=False,
            )

        articles = []
        for a in (art.get("articles") or [])[:limit]:
            title = a.get("title", "") or ""
            articles.append({
                "title": title,
                "url": a.get("url"),
                "domain": a.get("domain"),
                "published": a.get("seendate"),
                "source_country": a.get("sourcecountry"),
                "language": a.get("language"),
                "sentiment_hint": _tag(title),
            })

        # Best-effort aggregate tone; never fail the whole call if this 429s.
        sentiment: dict[str, Any] | None = None
        tone_url = _DOC_URL + "?" + urllib.parse.urlencode({
            "query": query, "mode": "TimelineTone", "format": "json", "timespan": timespan,
        })
        try:
            tl = _get_json(tone_url)
            series = (tl.get("timeline") or [{}])[0].get("data") or []
            vals = [float(p["value"]) for p in series if p.get("value") is not None]
            if vals:
                mean_tone = sum(vals) / len(vals)
                sentiment = {
                    "mean_tone": round(mean_tone, 3),
                    "label": _label_from_tone(mean_tone),
                    "n_points": len(vals),
                }
        except Exception as exc:  # noqa: BLE001 — tone is optional context
            logger.info("gdelt tone unavailable (%s); returning articles with lexicon hints", exc)

        payload = {
            "ok": True,
            "source": "gdelt",
            "query": query,
            "timespan": timespan,
            "sentiment": sentiment,
            "count": len(articles),
            "articles": articles,
        }
        payload = with_security_warnings(payload, fields=("articles.*.title",))
        return json.dumps(payload, ensure_ascii=False)
