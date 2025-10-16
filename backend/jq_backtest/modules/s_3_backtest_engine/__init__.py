"""回测引擎模块 - 核心协调器

提供完整的回测流程协调功能，包括：
- 策略编译
- 数据加载
- 参数配置
- 执行管理
- 结果收集

主要导出：
- run_backtest: 主回测入口函数
- select_pipeline_class: Pipeline选择器
- register_default_analyzers: 注册分析器
- run_strategy: 策略执行器
"""

from .engine import run_backtest, select_pipeline_class
from .executor import register_default_analyzers, run_strategy

__all__ = [
    # 主引擎函数
    "run_backtest",
    "select_pipeline_class",
    # 执行器函数
    "register_default_analyzers",
    "run_strategy",
]
