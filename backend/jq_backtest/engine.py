"""
Compatibility wrapper exposing JQBacktestEngine at `backend.jq_backtest.engine`.

This thin layer adapts older engine usage (tests and scripts) to the
new modular implementation under `backend.jq_backtest.modules.s_3_backtest_engine`.
"""
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.jq_backtest.modules.s_3_backtest_engine.engine import run_backtest as _run_backtest


class JQBacktestEngine:
    def __init__(self, csv_provider: Optional[Any] = None):
        # csv_provider kept for API compatibility; new modules read from data dirs
        self.csv_provider = csv_provider

    def run_backtest(
        self,
        strategy_code: str,
        securities: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = 'daily',
        initial_cash: float = 100000,
        fq: str = 'pre',
        **kwargs,
    ) -> Dict[str, Any]:
        """Run a backtest and return a serializable dict result.

        This wrapper selects the first security if a list is provided to
        match the older single-symbol runner.
        """
        if securities:
            symbol = securities[0]
        else:
            symbol = kwargs.get('symbol') or ''

        # normalize dates to strings
        def _datestr(d):
            if isinstance(d, datetime):
                return d.strftime('%Y-%m-%d')
            return str(d) if d is not None else ''

        start = _datestr(start_date or kwargs.get('start_date') or kwargs.get('start'))
        end = _datestr(end_date or kwargs.get('end_date') or kwargs.get('end'))

        # delegate to modular run_backtest
        result = _run_backtest(
            symbol,
            start,
            end,
            initial_cash,
            strategy_code,
            strategy_params=kwargs.get('strategy_params'),
            benchmark_symbol=kwargs.get('benchmark_symbol'),
            frequency=freq,
            adjust_type=kwargs.get('adjust_type', 'auto'),
            datadir=kwargs.get('datadir', 'data'),
        )

        # Normalize return value to a flat dict compatible with older runner
        try:
            structured = asdict(result)
            # Pull up metrics into top-level keys for backward compatibility
            metrics = structured.pop('metrics', {}) or {}
            flattened = {**metrics, **structured}

            # Ensure convenience numeric keys exist (some callers expect them)
            try:
                flattened['final_value'] = float(flattened.get('final_value', result.final_value))
            except Exception:
                pass
            try:
                flattened['total_return'] = float(flattened.get('total_return', result.total_return))
            except Exception:
                pass

            # Provide common legacy keys with safe defaults to avoid KeyError in
            # older callers/tests when metrics are missing (e.g., no trades).
            legacy_keys_defaults = {
                'annualized_return': 0.0,
                'max_drawdown': 0.0,
                'sharpe_ratio': 0.0,
                'total_trades': 0,
                'win_rate': 0.0,
            }

            for k, dv in legacy_keys_defaults.items():
                if k not in flattened:
                    # try a few alternative metric names
                    alt = metrics.get(k) if isinstance(metrics, dict) else None
                    if alt is None:
                        flattened[k] = dv
                    else:
                        try:
                            flattened[k] = type(dv)(alt)
                        except Exception:
                            flattened[k] = dv

            # Provide initial_cash (some older callers expect this top-level)
            try:
                flattened.setdefault('initial_cash', float(initial_cash))
            except Exception:
                flattened.setdefault('initial_cash', 0.0)

            # Provide positions: if the modular engine doesn't produce the
            # legacy 'positions' flattened list, provide empty list to avoid
            # KeyError in tests that access it.
            flattened.setdefault('positions', structured.get('positions', []) if isinstance(structured, dict) else [])

            return flattened
        except Exception:
            # If result is already a dict or not a dataclass
            if isinstance(result, dict):
                return result
            return {"result": str(result)}


__all__ = ['JQBacktestEngine']
