"""Tests for the portfolio risk x-ray core and its agent tool."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from backtest.risk_xray import compute_risk_xray
from src.tools.portfolio_risk_tool import PortfolioRiskXrayTool


def _closes(series_map: dict[str, list[float]], start: str = "2026-01-01") -> pd.DataFrame:
    n = max(len(v) for v in series_map.values())
    idx = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame({k: pd.Series(v, index=idx[: len(v)]) for k, v in series_map.items()})


def _assert_strict_json(payload: dict) -> None:
    json.dumps(payload, allow_nan=False)


# ---------------------------------------------------------------------------
# weights handling
# ---------------------------------------------------------------------------


def test_weights_are_renormalized_with_warning():
    closes = _closes({"AAA": list(range(100, 160)), "BBB": list(range(50, 110))})
    result = compute_risk_xray(closes, {"AAA": 2.0, "BBB": 2.0}, min_history=10)
    assert result["inputs"]["weights"] == {"AAA": 0.5, "BBB": 0.5}
    assert any("renormalized" in w for w in result["warnings"])
    _assert_strict_json(result)


def test_negative_weight_rejected():
    closes = _closes({"AAA": list(range(100, 160)), "BBB": list(range(50, 110))})
    with pytest.raises(ValueError, match="long-only"):
        compute_risk_xray(closes, {"AAA": 1.5, "BBB": -0.5})


def test_unknown_symbol_rejected():
    closes = _closes({"AAA": list(range(100, 160))})
    with pytest.raises(ValueError, match="no price data"):
        compute_risk_xray(closes, {"AAA": 0.5, "MISSING": 0.5})


def test_empty_panel_rejected():
    with pytest.raises(ValueError, match="empty"):
        compute_risk_xray(pd.DataFrame(), {"AAA": 1.0})


# ---------------------------------------------------------------------------
# concentration
# ---------------------------------------------------------------------------


def test_concentration_math():
    closes = _closes(
        {
            "AAA": list(range(100, 160)),
            "BBB": list(range(50, 110)),
            "CCC": list(range(200, 260)),
        }
    )
    result = compute_risk_xray(closes, {"AAA": 0.5, "BBB": 0.25, "CCC": 0.25}, min_history=10)
    conc = result["concentration"]
    assert conc["hhi"] == pytest.approx(0.375)
    assert conc["effective_n"] == pytest.approx(1 / 0.375)
    assert conc["top1_weight"] == pytest.approx(0.5)
    assert conc["top3_weight"] == pytest.approx(1.0)
    _assert_strict_json(result)


# ---------------------------------------------------------------------------
# history filter and calendar alignment
# ---------------------------------------------------------------------------


def test_thin_symbol_skipped_and_weights_renormalized():
    closes = _closes(
        {
            "AAA": list(range(100, 160)),
            "BBB": list(range(50, 110)),
            "THIN": [10.0] * 5,
        }
    )
    result = compute_risk_xray(
        closes, {"AAA": 0.34, "BBB": 0.33, "THIN": 0.33}, min_history=30
    )
    assert [s["symbol"] for s in result["skipped"]] == ["THIN"]
    assert result["inputs"]["symbols"] == ["AAA", "BBB"]
    assert result["inputs"]["weights"] == pytest.approx({"AAA": 0.34 / 0.67, "BBB": 0.33 / 0.67})
    _assert_strict_json(result)


def test_all_thin_rejected():
    closes = _closes({"AAA": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="valid bars"):
        compute_risk_xray(closes, {"AAA": 1.0}, min_history=30)


# ---------------------------------------------------------------------------
# drawdown / tail risk
# ---------------------------------------------------------------------------


def test_max_drawdown_on_hand_built_curve():
    closes = _closes({"AAA": [100.0, 120.0, 60.0, 90.0]})
    result = compute_risk_xray(closes, {"AAA": 1.0}, min_history=2)
    assert result["drawdown"]["max_drawdown"] == pytest.approx(-0.5)
    _assert_strict_json(result)


def test_expected_shortfall_on_known_tail():
    returns_closes = [100.0]
    for ret in [0.01] * 19 + [-0.10]:
        returns_closes.append(returns_closes[-1] * (1 + ret))
    closes = _closes({"AAA": returns_closes})
    result = compute_risk_xray(closes, {"AAA": 1.0}, min_history=2)
    tail = result["tail_risk"]
    assert tail["expected_shortfall_95"] == pytest.approx(0.10)
    assert tail["var_95"] is not None
    _assert_strict_json(result)


# ---------------------------------------------------------------------------
# correlation / beta / diversification
# ---------------------------------------------------------------------------


def test_equal_weight_beta_is_one_against_equal_weight_proxy():
    rng = np.random.default_rng(7)
    a = rng.normal(0.001, 0.01, 80)
    b = rng.normal(0.0005, 0.02, 80)
    closes = _closes(
        {
            "AAA": 100 * np.cumprod(1 + a),
            "BBB": 80 * np.cumprod(1 + b),
        }
    )
    result = compute_risk_xray(closes, {"AAA": 0.5, "BBB": 0.5}, min_history=10)
    assert result["correlation"]["beta_to_equal_weight"] == pytest.approx(1.0)
    _assert_strict_json(result)


def test_identical_series_have_unit_diversification_ratio():
    base = 100 * np.cumprod(1 + np.random.default_rng(3).normal(0, 0.01, 80))
    closes = _closes({"AAA": base, "BBB": base.copy()})
    result = compute_risk_xray(closes, {"AAA": 0.5, "BBB": 0.5}, min_history=10)
    assert result["diversification"]["diversification_ratio"] == pytest.approx(1.0)
    assert result["correlation"]["avg_pairwise_abs"] == pytest.approx(1.0)
    _assert_strict_json(result)


def test_single_asset_correlation_section_is_null():
    closes = _closes({"AAA": list(range(100, 180))})
    result = compute_risk_xray(closes, {"AAA": 1.0}, min_history=10)
    corr = result["correlation"]
    assert corr["avg_pairwise_abs"] is None
    assert corr["beta_to_equal_weight"] is None
    assert corr["note"]
    _assert_strict_json(result)


def test_constant_prices_never_emit_nan():
    closes = _closes({"AAA": [10.0] * 60, "BBB": [20.0] * 60})
    result = compute_risk_xray(closes, {"AAA": 0.5, "BBB": 0.5}, min_history=10)
    _assert_strict_json(result)


# ---------------------------------------------------------------------------
# agent tool
# ---------------------------------------------------------------------------


def _stub_fetcher(closes_map: dict[str, list[float]]):
    def fetch(*, codes, start_date, end_date, source, interval, **kwargs):
        out: dict[str, object] = {}
        idx = pd.date_range("2026-01-01", periods=max(len(v) for v in closes_map.values()), freq="D")
        for code in codes:
            values = closes_map.get(code)
            if values is None:
                continue
            out[code] = [
                {"date": str(idx[i].date()), "close": price} for i, price in enumerate(values)
            ]
        out["_unresolved"] = [c for c in codes if c not in out]
        return out

    return fetch


def test_tool_happy_path_equal_weights():
    tool = PortfolioRiskXrayTool(
        data_fetcher=_stub_fetcher(
            {"AAA": list(range(100, 160)), "BBB": list(range(50, 110))}
        )
    )
    payload = json.loads(
        tool.execute(symbols=["AAA", "BBB"], start_date="2026-01-01", end_date="2026-03-01")
    )
    assert payload["status"] == "ok"
    assert payload["data"]["concentration"]["hhi"] == pytest.approx(0.5)
    assert payload["data"]["concentration"]["effective_n"] == pytest.approx(2.0)
    assert payload["meta"]["unresolved_symbols"] == []


def test_tool_reports_unresolved_symbols():
    tool = PortfolioRiskXrayTool(data_fetcher=_stub_fetcher({"AAA": list(range(100, 160))}))
    payload = json.loads(tool.execute(symbols=["AAA", "NOPE"]))
    # NOPE has no data → weights reference it → error envelope, still strict JSON
    assert payload["status"] == "error"
    assert "NOPE" in payload["error"]


def test_tool_rejects_bad_arguments():
    tool = PortfolioRiskXrayTool(data_fetcher=_stub_fetcher({}))
    payload = json.loads(tool.execute(symbols=[]))
    assert payload["status"] == "error"
    payload = json.loads(tool.execute(symbols=["AAA"], weights={"AAA": 0.5, "ZZZ": 0.5}))
    assert payload["status"] == "error"
    payload = json.loads(
        tool.execute(symbols=["AAA"], start_date="2026-03-01", end_date="2026-01-01")
    )
    assert payload["status"] == "error"


def test_tool_survives_records_without_dates():
    def fetch(*, codes, start_date, end_date, source, interval, **kwargs):
        return {
            "AAA": [{"close": 100 + i} for i in range(40)],  # no date fields at all
            # partially dated → whole series falls back to loader order
            "BBB": (
                [{"date": "2026-02-01", "close": 50.0}]
                + [{"close": 50 + i} for i in range(1, 40)]
            ),
        }

    tool = PortfolioRiskXrayTool(data_fetcher=fetch)
    payload = json.loads(tool.execute(symbols=["AAA", "BBB"]))
    assert payload["status"] == "ok"
