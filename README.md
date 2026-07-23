# Paper Trading BOTo

An event-driven paper trading bot: backtest strategies against a simulated
broker, then run the identical strategy code live against an Interactive
Brokers paper account.

**Start with the package README:
[paper_trading_boto/README.md](paper_trading_boto/README.md)** — it covers
the architecture, installation (`pip install -e '.[dev]'`), and the
`boto backtest | live | webhook` CLI.

## Repository layout

- `paper_trading_boto/` — the package: engine, brokers (simulated + IBKR),
  data feeds, strategies, risk management, webhook service.
- `tests/` — pytest suite; runs offline, no IBKR or network needed.
- `pyproject.toml` — packaging and dependencies (single source of truth).
- `.env.example` — configuration template; copy to `.env`.
- `docs/` — **historical**: documentation for the pre-redesign architecture,
  kept for reference. Where it conflicts with the package README, the
  package README is correct.
- `paper_trading_boto/dashboard.py` — **non-functional**: Streamlit UI from
  the old architecture, kept for a future port to the event-driven engine.

## Quick start

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
boto backtest --symbol AAPL --start 2024-01-01 --end 2025-01-01
```

## Disclaimer

Educational use only. Algorithmic trading carries significant financial
risk; nothing here is financial advice.
