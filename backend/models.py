"""
Compatibility shim: expose models from `backend.jq_backtest.models` under
the legacy import path `backend.models`.

This file keeps the migration confined to the `backend/` folder by providing
the expected module for older imports used throughout the tests and other
modules.
"""
from warnings import warn as _warn
_warn(
	"backend.models is a compatibility shim and is deprecated. Use backend.jq_backtest.models instead.",
	DeprecationWarning,
)
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Import actual definitions from the relocated module
from backend.jq_backtest import models as _jq_models

# Re-export the key model classes expected by older code
TradeRecord = _jq_models.TradeRecord
OrderRecord = _jq_models.OrderRecord
BacktestResult = _jq_models.BacktestResult

__all__ = ["TradeRecord", "OrderRecord", "BacktestResult"]
