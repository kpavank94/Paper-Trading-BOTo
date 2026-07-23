"""CSV and HTML report generation.

Ported from the original module to consume :class:`Fill` and
:class:`Portfolio` (fills are the trade ledger now) and to accept an
optional backtest metrics dict rendered above the tables.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from tabulate import tabulate

from .events import Fill
from .portfolio import Portfolio


class ReportGenerator:
    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _fill_rows(fills: List[Fill]) -> List[dict]:
        return [
            {
                "timestamp": fill.timestamp.isoformat(),
                "symbol": fill.symbol,
                "action": fill.side.value,
                "quantity": fill.quantity,
                "price": fill.price,
                "commission": fill.commission,
            }
            for fill in fills
        ]

    def generate_csv(self, fills: List[Fill], portfolio: Portfolio) -> str:
        """Write trades and positions CSVs; returns the trades file path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trades_file = self.output_dir / f"trades_{timestamp}.csv"
        positions_file = self.output_dir / f"positions_{timestamp}.csv"
        pd.DataFrame(self._fill_rows(fills)).to_csv(trades_file, index=False)
        pd.DataFrame.from_dict(portfolio.summary(), orient="index").to_csv(positions_file)
        return str(trades_file)

    def generate_html(
        self,
        fills: List[Fill],
        portfolio: Portfolio,
        metrics: Optional[Dict[str, float]] = None,
    ) -> str:
        """Write an HTML report; returns its file path."""
        trades_table = tabulate(
            [
                [
                    fill.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    fill.symbol,
                    fill.side.value,
                    fill.quantity,
                    f"{fill.price:.2f}",
                    f"{fill.commission:.2f}",
                ]
                for fill in fills
            ],
            headers=["Timestamp", "Symbol", "Action", "Quantity", "Price", "Commission"],
            tablefmt="html",
        )
        positions_table = tabulate(
            [
                [symbol, info["quantity"], f"{info['avg_cost']:.2f}",
                 f"{info['realized_pnl']:.2f}"]
                for symbol, info in portfolio.summary().items()
            ],
            headers=["Symbol", "Quantity", "Avg Cost", "Realized PnL"],
            tablefmt="html",
        )
        metrics_section = ""
        if metrics:
            metrics_table = tabulate(
                sorted(metrics.items()), headers=["Metric", "Value"], tablefmt="html"
            )
            metrics_section = f"<h2>Backtest Metrics</h2>\n    {metrics_table}"
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>BOTo Trading Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 8px; }}
        th {{ background-color: #f2f2f2; }}
        h2 {{ color: #333; }}
    </style>
</head>
<body>
    <h1>BOTo Trading Report</h1>
    {metrics_section}
    <h2>Trade History</h2>
    {trades_table}
    <h2>Positions Summary</h2>
    {positions_table}
</body>
</html>
"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file = self.output_dir / f"report_{timestamp}.html"
        html_file.write_text(html_content)
        return str(html_file)
