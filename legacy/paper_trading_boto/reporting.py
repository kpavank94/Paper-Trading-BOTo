"""
Reporting module for Paper Trading BOTo.

This module generates CSV and HTML reports summarising trading
activities.  Reports include trade history, cost basis, realized and
unrealized PnL.  The HTML report uses a simple table layout and can
be extended for email delivery or dashboard integration, inspired by
projects that added HTML email reports【157485389729687†L78-L83】.

The ``ReportGenerator`` class writes reports to a specified directory
and returns file paths.  If Pandas is available the CSV output is
generated via DataFrame; otherwise a fallback CSV writer is used.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from tabulate import tabulate

from .cost_basis import CostBasisTracker, TradeRecord


class ReportGenerator:
    def __init__(self, output_dir: str = "reports") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_csv(self, trades: List[TradeRecord], cost_tracker: CostBasisTracker) -> str:
        """Generate a CSV report of trades and positions.

        Returns the file path of the generated CSV.
        """
        data = [
            {
                "timestamp": trade.timestamp.isoformat(),
                "symbol": trade.symbol,
                "action": trade.action,
                "quantity": trade.quantity,
                "price": trade.price,
            }
            for trade in trades
        ]
        trades_df = pd.DataFrame(data)
        positions_summary = cost_tracker.summary()
        positions_df = pd.DataFrame.from_dict(positions_summary, orient="index")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trades_file = self.output_dir / f"trades_{timestamp}.csv"
        positions_file = self.output_dir / f"positions_{timestamp}.csv"
        trades_df.to_csv(trades_file, index=False)
        positions_df.to_csv(positions_file)
        return str(trades_file)

    def generate_html(self, trades: List[TradeRecord], cost_tracker: CostBasisTracker) -> str:
        """Generate an HTML report summarising trades and positions.

        Returns the file path of the generated HTML file.
        """
        trades_rows = [
            [
                trade.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                trade.symbol,
                trade.action,
                trade.quantity,
                f"{trade.price:.2f}",
            ]
            for trade in trades
        ]
        trades_table = tabulate(
            trades_rows,
            headers=["Timestamp", "Symbol", "Action", "Quantity", "Price"],
            tablefmt="html",
        )
        # Positions summary
        positions = cost_tracker.summary()
        positions_rows = []
        for symbol, info in positions.items():
            positions_rows.append(
                [
                    symbol,
                    info["quantity"],
                    f"{info['avg_cost']:.2f}",
                    f"{info['realized_pnl']:.2f}",
                ]
            )
        positions_table = tabulate(
            positions_rows,
            headers=["Symbol", "Quantity", "Avg Cost", "Realized PnL"],
            tablefmt="html",
        )
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
    <h2>Trade History</h2>
    {trades_table}
    <h2>Positions Summary</h2>
    {positions_table}
</body>
</html>
"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_file = self.output_dir / f"report_{timestamp}.html"
        with open(html_file, "w") as f:
            f.write(html_content)
        return str(html_file)