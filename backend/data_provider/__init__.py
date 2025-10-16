"""
Compatibility export for SimpleCSVDataProvider.

This module intentionally re-exports the new adapter implementation so that
existing imports such as `from backend.data_provider import SimpleCSVDataProvider`
continue to work. The legacy implementation `simple_provider.py` remains in the
repository for now to allow safe rollback, but new code should import the
adapter directly.
"""
from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider

try:
	# Prefer the legacy detailed shim which exposes attributes/tests expect
	from .simple_provider import SimpleCSVDataProvider  # type: ignore
except Exception:
	from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider

__all__ = ["SimpleCSVDataProvider"]

