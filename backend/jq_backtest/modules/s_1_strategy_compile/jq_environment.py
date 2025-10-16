"""聚宽兼容执行环境：为用户策略提供仿真的全局变量与受限导入机制。"""
from __future__ import annotations

from functools import partial
from typing import Any, Dict

import backtrader as bt
import pandas as pd

from backend.modules.utils import stock_pool
from backend.modules.s_1_strategy_compile import jq_api as jq_api_module
from backend.modules.s_1_strategy_compile.jq_models import GlobalVariableContainer, JQLogger
from backend.modules.s_1_strategy_compile.utils import load_trading_calendar

__all__ = [
    "ALLOWED_GLOBALS",
    "IMPORT_WHITELIST",
    "limited_import",
    "build_jq_compat_env",
]


def _unbound(name: str):
    def _raise(*_args, **_kwargs):
        raise RuntimeError(f"{name} 仅能在聚宽策略运行环境初始化后使用")

    return _raise


run_daily = _unbound("run_daily")
run_weekly = _unbound("run_weekly")
run_monthly = _unbound("run_monthly")
before_trading_start = _unbound("before_trading_start")
after_trading_end = _unbound("after_trading_end")
set_commission = _unbound("set_commission")
get_current_data = _unbound("get_current_data")

ALLOWED_GLOBALS: Dict[str, Any] = {
    "__builtins__": {
        "abs": abs,
        "min": min,
        "max": max,
        "range": range,
        "len": len,
        "sum": sum,
        "enumerate": enumerate,
        "zip": zip,
        "float": float,
        "int": int,
        "str": str,
        "list": list,
        "tuple": tuple,
        "dict": dict,
        "set": set,
        "bool": bool,
        "isinstance": isinstance,
        "print": print,
        "__build_class__": __build_class__,
        "__name__": "__main__",
    },
    "bt": bt,
    "pd": pd,
    "get_index_stocks": stock_pool.get_index_stocks,
    "get_index_weights": stock_pool.get_index_weights,
    "get_industry_stocks": stock_pool.get_industry_stocks,
    "get_concept_stocks": stock_pool.get_concept_stocks,
    "get_all_securities": stock_pool.get_all_securities,
    "run_daily": run_daily,
    "run_weekly": run_weekly,
    "run_monthly": run_monthly,
    "before_trading_start": before_trading_start,
    "after_trading_end": after_trading_end,
    "get_current_data": get_current_data,
}

IMPORT_WHITELIST: Dict[str, Any] = {
    "backtrader": bt,
    "pandas": pd,
    "math": __import__("math"),
    "statistics": __import__("statistics"),
    "numpy": None,
}


def limited_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: D401
    """受限导入函数：仅允许白名单模块被用户策略导入。"""

    root = name.split(".")[0]
    if root not in IMPORT_WHITELIST:
        raise ImportError(f"不允许导入模块: {name}")
    if root == "numpy" and IMPORT_WHITELIST[root] is None:
        IMPORT_WHITELIST[root] = __import__(root)
    return __import__(name, globals, locals, fromlist, level)


ALLOWED_GLOBALS["__builtins__"]["__import__"] = limited_import


def build_jq_compat_env(target_dict: Dict[str, Any]) -> Dict[str, Any]:
    """为目标字典填充聚宽兼容的工具函数，并返回 ``jq_state`` 状态字典。"""

    # ① 创建状态容器
    g = GlobalVariableContainer()
    jq_state: Dict[str, Any] = {
        "benchmark": None,
        "options": {
            "enable_limit_check": True,
            "limit_up_factor": 1.10,
            "limit_down_factor": 0.90,
            "price_tick": 0.01,
            "limit_pct": 0.10,
        },
        "records": [],
        "log": [],
        "g": g,
        "history_df": None,
        "history_df_map": {},
        "minute_daily_cache": {},
        "current_dt": None,
        "user_start": None,
        "in_warmup": False,
        "blocked_orders": [],
        "trading_calendar": None,
    }

    # ② 加载交易日历
    trading_cal = load_trading_calendar()
    if trading_cal:
        jq_state["trading_calendar"] = trading_cal
        jq_state["log"].append(f"[trading_calendar_loaded] size={len(trading_cal)}")

    # ③ 创建日志器
    log_obj = JQLogger(jq_state)
    jq_state["logger"] = log_obj

    # ④ 使用 partial 创建包装函数
    set_benchmark = partial(jq_api_module.set_benchmark, jq_state=jq_state)
    set_option = partial(jq_api_module.set_option, jq_state=jq_state)
    record = partial(jq_api_module.record, jq_state=jq_state)
    set_commission = partial(jq_api_module.set_commission, jq_state=jq_state)
    get_current_data_wrapper = partial(jq_api_module.get_current_data, jq_state=jq_state)
    run_daily_wrapper = partial(jq_api_module.run_daily, jq_state=jq_state)
    run_weekly_wrapper = partial(jq_api_module.run_weekly, jq_state=jq_state)
    run_monthly_wrapper = partial(jq_api_module.run_monthly, jq_state=jq_state)
    before_trading_start_wrapper = partial(jq_api_module.before_trading_start, jq_state=jq_state)
    after_trading_end_wrapper = partial(jq_api_module.after_trading_end, jq_state=jq_state)

    # set_slippage 需要特殊处理（多个可选参数）
    def set_slippage(obj=None, type=None, ref=None):  # noqa: A002, D401
        jq_api_module.set_slippage(obj=obj, type=type, ref=ref, jq_state=jq_state)

    # ⑤ 注入依赖（删除冗余的运行时错误占位符）
    target_dict.update(
        {
            "g": g,
            "set_benchmark": set_benchmark,
            "set_option": set_option,
            "set_slippage": set_slippage,
            "set_commission": set_commission,
            "record": record,
            "log": log_obj,
            "jq_state": jq_state,
            "get_index_stocks": stock_pool.get_index_stocks,
            "get_index_weights": stock_pool.get_index_weights,
            "get_industry_stocks": stock_pool.get_industry_stocks,
            "get_concept_stocks": stock_pool.get_concept_stocks,
            "get_all_securities": stock_pool.get_all_securities,
            "get_current_data": get_current_data_wrapper,
            "run_daily": run_daily_wrapper,
            "run_weekly": run_weekly_wrapper,
            "run_monthly": run_monthly_wrapper,
            "before_trading_start": before_trading_start_wrapper,
            "after_trading_end": after_trading_end_wrapper,
        }
    )
    
    return jq_state

