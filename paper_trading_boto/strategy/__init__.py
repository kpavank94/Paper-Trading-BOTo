from .base import Strategy
from .sma_crossover import SMACrossoverStrategy

STRATEGIES = {
    "sma_crossover": SMACrossoverStrategy,
}

__all__ = ["Strategy", "SMACrossoverStrategy", "STRATEGIES"]
