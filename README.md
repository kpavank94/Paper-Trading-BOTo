# Paper Trading BOTo

Welcome to **Paper Trading BOTo**. This repository contains the source code, documentation and tests for a paper trading framework that connects to Interactive Brokers through the `ib_insync` library.

## Documentation

The primary documentation has moved to the `docs` directory. Start with [docs/overview.md](docs/overview.md) for a comprehensive introduction and [docs/FAQ.md](docs/FAQ.md) for frequently asked questions.

## Repository layout

- `paper_trading_boto/` – Python package containing the bot code, interfaces, strategies and services.
- `docs/` – Markdown documentation, including the overview and FAQ.
- `tests/` – Unit tests for the codebase (requires `pytest`).
- `requirements.txt` – Python dependencies.
- `.env.example` – Template for environment variables used by the bot and services.

Use the navigation tree on the left to expand these directories when browsing via the GitHub web interface.

## Getting started

Clone the repository, create a virtual environment and install dependencies using the root `requirements.txt`:

```sh
git clone https://github.com/your-username/paper-trading-boto.git
cd paper-trading-boto
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

See the documentation in `docs/` and explore the `paper_trading_boto` package for usage instructions.
