"""Broker adapters. Import the concrete classes lazily to keep optional
dependencies (ib_insync, alpaca-py) out of the import path when unused."""

from __future__ import annotations

from ..config import Settings
from .base import Broker, Intent, plan_orders

__all__ = ["Broker", "Intent", "plan_orders", "build_broker"]


def build_broker(settings: Settings) -> Broker:
    name = settings.broker.lower()
    if name == "alpaca":
        from .alpaca import AlpacaBroker

        return AlpacaBroker(settings)
    if name == "ibkr":
        from .ibkr import IBKRBroker

        return IBKRBroker(settings)
    raise ValueError(f"unknown broker '{settings.broker}', expected 'alpaca' or 'ibkr'")
