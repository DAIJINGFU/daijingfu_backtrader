"""策略编译模块公共接口。

提供聚宽风格的策略编译、上下文对象和API函数。
"""

# 模型类
from .jq_models import (
    SubPortfolioPosition,
    Portfolio,
    Context,
    PanelDataEmulator,
)
from .utils import normalize_code, parse_date, round_to_price_tick
from .jq_api import (
    attribute_history,
    get_current_data,
    get_price,
    history,
    order,
    order_target,
    order_value,
    order_target_value,
    order_target_percent,
    record,
    run_daily,
    run_weekly,
    run_monthly,
    before_trading_start,
    after_trading_end,
    set_benchmark,
    set_option,
    set_slippage,
    set_commission,
)

# 编译器主函数（暂未实现，留待后续）
# from .compiler import compile_user_strategy

__all__ = [
    # 模型类
    "SubPortfolioPosition",
    "Portfolio",
    "Context",
    "PanelDataEmulator",
    # 工具函数
    "normalize_code",
    "parse_date",
    "round_to_price_tick",
    # API函数
    "get_price",
    "attribute_history",
    "history",
    "get_current_data",
    "order",
    "order_value",
    "order_target",
    "order_target_value",
    "order_target_percent",
    "record",
    "run_daily",
    "run_weekly",
    "run_monthly",
    "before_trading_start",
    "after_trading_end",
    "set_benchmark",
    "set_option",
    "set_slippage",
    "set_commission",
    # 编译器（暂未导出）
    # "compile_user_strategy",
]

