"""统一模块导入 - 让开发人员轻松使用各模块功能

现在模块名已规范化（添加 s_ 前缀），可以直接导入。

使用示例：
    # 方式1：从主模块导入所有功能
    from backend.modules import (
        compile_user_strategy,      # 策略编译
        run_backtest,                # 回测执行
        build_formatter,             # 结果格式化
        load_bt_feed,                # 数据加载
    )
    
    # 方式2：从子模块导入
    from backend.modules.s_1_strategy_compile import compile_user_strategy
    from backend.modules.s_3_backtest_engine import run_backtest
"""

# ============================================================================
# 第1步：策略编译模块
# ============================================================================
from .s_1_strategy_compile.compiler import compile_user_strategy
from .s_1_strategy_compile.jq_models import (
    Portfolio,
    Context,
    SubPortfolioPosition,
    PanelDataEmulator,
)
from .s_1_strategy_compile.jq_api import (
    # 数据获取 API
    get_price,
    attribute_history,
    history,
    get_current_data,
    # 交易下单 API
    order,
    order_value,
    order_target,
    order_target_value,
    order_target_percent,
    # 调度器 API
    run_daily,
    run_weekly,
    run_monthly,
    # 生命周期 API
    before_trading_start,
    after_trading_end,
    # 配置 API
    set_benchmark,
    set_option,
    set_slippage,
    set_commission,
    # 记录 API
    record,
)

# ============================================================================
# 第2步：数据加载模块
# ============================================================================
from .s_2_data_loader.csv_loader import (
    DataNotFound,
    normalize_symbol,
    resolve_price_file,
    load_price_dataframe,
    load_bt_feed,
)
from .s_2_data_loader.data_pipeline import prepare_data_sources
from .s_2_data_loader.minute_cache import (
    CacheConfig,
    MinuteAggregationCache,
    aggregate_minute_dataframe,
    build_cache_key,
)

# ============================================================================
# 第3步：回测执行模块
# ============================================================================
from .s_3_backtest_engine.engine import (
    run_backtest,
    select_pipeline_class,
)
from .s_3_backtest_engine.executor import (
    register_default_analyzers,
    run_strategy,
)

# ============================================================================
# 第4步：结果处理模块
# ============================================================================
from .s_4_result_processor.analyzer import (
    compute_metrics_and_curves,
    collect_trade_and_order_details,
)
from .s_4_result_processor.formatter import (
    FormatterPayload,
    BaseResultFormatter,
    DailyResultFormatter,
    IntradayResultFormatter,
    build_formatter,
)
from .s_4_result_processor.reporter import (
    TradeCapture,
    create_order_capture_analyzer,
)

# ============================================================================
# 导出列表
# ============================================================================
__all__ = [
    # === 策略编译 ===
    "compile_user_strategy",
    "Portfolio",
    "Context",
    "SubPortfolioPosition",
    "PanelDataEmulator",
    # 聚宽 API
    "get_price",
    "attribute_history",
    "history",
    "get_current_data",
    "order",
    "order_value",
    "order_target",
    "order_target_value",
    "order_target_percent",
    "run_daily",
    "run_weekly",
    "run_monthly",
    "before_trading_start",
    "after_trading_end",
    "set_benchmark",
    "set_option",
    "set_slippage",
    "set_commission",
    "record",
    
    # === 数据加载 ===
    "DataNotFound",
    "normalize_symbol",
    "resolve_price_file",
    "load_price_dataframe",
    "load_bt_feed",
    "prepare_data_sources",
    "CacheConfig",
    "MinuteAggregationCache",
    "aggregate_minute_dataframe",
    "build_cache_key",
    
    # === 回测执行 ===
    "run_backtest",
    "select_pipeline_class",
    "register_default_analyzers",
    "run_strategy",
    
    # === 结果处理 ===
    "compute_metrics_and_curves",
    "collect_trade_and_order_details",
    "FormatterPayload",
    "BaseResultFormatter",
    "DailyResultFormatter",
    "IntradayResultFormatter",
    "build_formatter",
    "TradeCapture",
    "create_order_capture_analyzer",
]
