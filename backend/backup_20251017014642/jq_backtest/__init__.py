"""
JoinQuant-compatible backtest module based on backtrader

This module provides a JoinQuant-compatible API for backtesting strategies
using the backtrader framework, while leveraging the existing CSV data infrastructure.
"""

from typing import Optional
from backend.jq_backtest.context import g, OrderCost
from backend.jq_backtest.order import Order, OrderStyle

# Thread-local storage for current strategy instance
import threading
_current_strategy = threading.local()

def _get_current_strategy():
    """Get the currently active strategy instance"""
    if not hasattr(_current_strategy, 'strategy'):
        raise RuntimeError("No active strategy context. Trading functions must be called from within strategy code.")
    return _current_strategy.strategy

def _set_current_strategy(strategy):
    """Set the currently active strategy instance"""
    _current_strategy.strategy = strategy

def _clear_current_strategy():
    """Clear the currently active strategy instance"""
    if hasattr(_current_strategy, 'strategy'):
        del _current_strategy.strategy

# Global trading API functions
def order(security: str, amount: int, style: Optional[OrderStyle] = None, **kwargs) -> Optional[Order]:
    """Place an order for a security"""
    strategy = _get_current_strategy()
    return strategy.trading_api.order(security, amount, style, **kwargs)

def order_target(security: str, amount: int, style: Optional[OrderStyle] = None, **kwargs) -> Optional[Order]:
    """Adjust position to target amount"""
    strategy = _get_current_strategy()
    return strategy.trading_api.order_target(security, amount, style, **kwargs)

def order_value(security: str, value: float, style: Optional[OrderStyle] = None, **kwargs) -> Optional[Order]:
    """Place an order for a certain value"""
    strategy = _get_current_strategy()
    return strategy.trading_api.order_value(security, value, style, **kwargs)

def order_target_value(security: str, value: float, style: Optional[OrderStyle] = None, **kwargs) -> Optional[Order]:
    """Adjust position to target value"""
    strategy = _get_current_strategy()
    return strategy.trading_api.order_target_value(security, value, style, **kwargs)

def log(*args, **kwargs):
    """Log a message"""
    print(*args, **kwargs)

def set_benchmark(security: str):
    """Set the benchmark for the strategy"""
    strategy = _get_current_strategy()
    strategy.context.benchmark = security
    return True

def set_option(key: str, value):
    """Set a runtime option"""
    strategy = _get_current_strategy()
    strategy.context.set_option(key, value)
    return True

def set_commission(commission):
    """Set commission rate"""
    strategy = _get_current_strategy()
    if hasattr(commission, 'open_commission'):
        strategy.context.order_cost = commission
    else:
        strategy.context.commission_rate = commission
    return True

def set_slippage(slippage):
    """Set slippage"""
    # Slippage is handled by backtrader, just store in context
    strategy = _get_current_strategy()
    strategy.context.slippage = slippage
    return True

def set_order_cost(order_cost, type='stock'):
    """Set order cost (commission and other fees)"""
    strategy = _get_current_strategy()
    if hasattr(order_cost, 'open_commission'):
        # OrderCost object
        strategy.context.order_cost = order_cost
    else:
        # Legacy: just a commission rate
        from backend.jq_backtest.context import OrderCost
        strategy.context.order_cost = OrderCost(
            open_commission=order_cost,
            close_commission=order_cost,
            close_today_commission=order_cost
        )
    return True

def run_daily(func, time='open', reference_security=None):
    """Register a function to run daily (placeholder for compatibility)"""
    # In backtrader context, this would be handled by before_trading_start
    # Store for potential use
    strategy = _get_current_strategy()
    if not hasattr(strategy.context, '_run_daily_funcs'):
        strategy.context._run_daily_funcs = []
    strategy.context._run_daily_funcs.append({
        'func': func,
        'time': time,
        'reference_security': reference_security
    })
    return True

def run_weekly(func, weekday=1, time='open', reference_security=None):
    """Register a function to run weekly (placeholder for compatibility)"""
    strategy = _get_current_strategy()
    if not hasattr(strategy.context, '_run_weekly_funcs'):
        strategy.context._run_weekly_funcs = []
    strategy.context._run_weekly_funcs.append({
        'func': func,
        'weekday': weekday,
        'time': time,
        'reference_security': reference_security
    })
    return True

def run_monthly(func, tradingday=1, time='open', reference_security=None):
    """Register a function to run monthly (placeholder for compatibility)"""
    strategy = _get_current_strategy()
    if not hasattr(strategy.context, '_run_monthly_funcs'):
        strategy.context._run_monthly_funcs = []
    strategy.context._run_monthly_funcs.append({
        'func': func,
        'tradingday': tradingday,
        'time': time,
        'reference_security': reference_security
    })
    return True

# Note: Import engine separately to avoid circular dependencies
# from backend.jq_backtest.engine import JQBacktestEngine

__all__ = [
    'Context',
    'g',
    'Portfolio',
    'Position',
    'Order',
    'OrderStyle',
    'OrderCost',
    'MarketOrder',
    'LimitOrder',
    'StopOrder',
    'JQBacktestEngine',
    # Global trading functions
    'order',
    'order_target',
    'order_value',
    'order_target_value',
    'log',
    # Configuration functions
    'set_benchmark',
    'set_option',
    'set_commission',
    'set_slippage',
    'set_order_cost',
    # Scheduling functions
    'run_daily',
    'run_weekly',
    'run_monthly',
]
