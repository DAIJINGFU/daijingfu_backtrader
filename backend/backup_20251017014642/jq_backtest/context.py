"""Context and global state for JoinQuant-compatible strategies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, Optional, Tuple

from backend.jq_backtest.portfolio import Portfolio


@dataclass
class OrderCost:
    """Simplified order cost configuration similar to JoinQuant."""

    open_commission: float = 0.0003
    close_commission: float = 0.0003
    close_today_commission: float = 0.0003
    stamp_duty: float = 0.001
    min_commission: float = 5.0
    open_tax: float = 0.0
    close_tax: float | None = None

    def __post_init__(self) -> None:
        """Normalize JoinQuant aliases for tax-related fields."""
        if self.open_tax is None:
            self.open_tax = 0.0

        if self.close_tax is None:
            # No explicit close_tax provided – mirror stamp duty
            self.close_tax = self.stamp_duty
        else:
            # close_tax provided takes precedence over stamp_duty to match JoinQuant naming
            self.stamp_duty = self.close_tax


class GlobalVariables:
    """
    Global variables container (g object)
    Users can store any variables in this object
    """
    def __init__(self):
        self._vars: Dict[str, Any] = {}
    
    def __setattr__(self, name: str, value: Any) -> None:
        if name == '_vars':
            object.__setattr__(self, name, value)
        else:
            self._vars[name] = value
    
    def __getattr__(self, name: str) -> Any:
        if name == '_vars':
            return object.__getattribute__(self, '_vars')
        if name in self._vars:
            return self._vars[name]
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
    
    def __delattr__(self, name: str) -> None:
        if name in self._vars:
            del self._vars[name]
        else:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def reset(self) -> None:
        """Clear all stored variables."""
        self._vars.clear()

    def items(self) -> Iterable[Tuple[str, Any]]:
        """Iterate over stored key/value pairs."""
        return self._vars.items()


# Global g object for user variables
g = GlobalVariables()


class RunParams:
    """
    Strategy run parameters
    """
    def __init__(
        self,
        start_date: datetime,
        end_date: datetime,
        frequency: str = 'daily',
        initial_cash: float = 1000000,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.frequency = frequency
        self.initial_cash = initial_cash


class Context:
    """
    Strategy context object
    Contains account information, portfolio, and run parameters
    """
    def __init__(self, run_params: Optional[RunParams] = None):
        self.current_dt: Optional[datetime] = None
        self.previous_date: Optional[datetime] = None
        self.portfolio: Optional[Portfolio] = None
        self.run_params: Optional[RunParams] = run_params
        
        # Universe of securities
        self.universe: list[str] = []
        
        # Benchmark
        self.benchmark: Optional[str] = None
        
        # Options
        self.options: Dict[str, Any] = {
            'use_real_price': False,
            'order_volume_ratio': 0.25,
        }

        # Trading cost configuration
        self.order_cost: OrderCost = OrderCost()
        self.commission_rate: float = self.order_cost.open_commission
        self.stamp_duty_rate: float = self.order_cost.stamp_duty
    
    def set_option(self, key: str, value: Any) -> None:
        """Set an option"""
        self.options[key] = value
    
    def get_option(self, key: str, default: Any = None) -> Any:
        """Get an option"""
        return self.options.get(key, default)


def reset_global_state() -> None:
    """Reset global JoinQuant state between strategy runs."""

    g.reset()
