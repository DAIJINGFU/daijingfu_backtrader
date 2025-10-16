"""
Compatibility shim package `backend.modules`.

This module aliases submodules from `backend.jq_backtest.modules` so older
imports like `from backend.modules.s_2_data_loader import ...` continue to work
after migrating code under `backend/jq_backtest/modules`.
"""
import warnings as _warnings
_warnings.warn(
    "backend.modules is a compatibility shim and is deprecated. Use backend.jq_backtest.modules instead.",
    DeprecationWarning,
    stacklevel=2,
)
import importlib
import sys

_submodules = [
    's_1_strategy_compile',
    's_2_data_loader',
    's_3_backtest_engine',
    's_4_result_processor',
    'utils',
]

for _name in _submodules:
    src = f'backend.jq_backtest.modules.{_name}'
    try:
        mod = importlib.import_module(src)
    except Exception:
        # defer import errors until real import is attempted
        continue
    # register under the old package name so `import backend.modules.s_2_data_loader` works
    sys.modules[f'backend.modules.{_name}'] = mod
    # also expose as attribute of this package
    globals()[_name] = mod

__all__ = _submodules
