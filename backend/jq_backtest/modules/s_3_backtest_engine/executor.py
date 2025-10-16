"""回测执行模块 - 注册分析器并运行策略

该模块主要承担两项职责：
1. 统一向 Cerebro 注入一组基础分析器，使得回测输出包含夏普比、最大回撤、交易概览等
   常见指标，同时挂载自定义的 TradeCapture 与订单捕获器，便于复刻聚宽平台的成交记录
2. 负责将策略类与参数添加到 Cerebro 并触发运行，返回实际使用的策略实例对象，
   为后续结果抽取与统计提供入口
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

import backtrader as bt

from ..s_4_result_processor.reporter import TradeCapture, create_order_capture_analyzer


__all__ = [
    "register_default_analyzers",
    "run_strategy",
]


def register_default_analyzers(
    cerebro: bt.Cerebro,
    jq_state: Dict[str, Any]
) -> None:
    """向 Cerebro 注册一组默认分析器，便于聚宽风格的回测指标统计
    
    Args:
        cerebro: Backtrader的Cerebro实例
        jq_state: 聚宽状态字典，用于构造订单捕获器（存放共享的订单列表与日志）
        
    Notes:
        分析器命名采用 _name 形式，便于 results_pipeline 在后续统一读取
        
    注册的分析器包括：
    - SharpeRatio: 夏普比率
    - DrawDown: 最大回撤
    - TradeAnalyzer: 交易统计
    - Returns: 收益率
    - TimeReturn: 时间序列收益
    - TradeCapture: 自定义交易捕获器
    - OrderCapture: 自定义订单捕获器
    """
    
    # 标准指标分析器 - 保证基础风险收益分析可用
    cerebro.addanalyzer(
        bt.analyzers.SharpeRatio,
        _name="sharpe",
        timeframe=bt.TimeFrame.Days
    )
    cerebro.addanalyzer(
        bt.analyzers.DrawDown,
        _name="drawdown"
    )
    cerebro.addanalyzer(
        bt.analyzers.TradeAnalyzer,
        _name="trades"
    )
    cerebro.addanalyzer(
        bt.analyzers.Returns,
        _name="returns"
    )
    cerebro.addanalyzer(
        bt.analyzers.TimeReturn,
        _name="timereturn"
    )
    
    # 自定义交易/订单捕获器（含中文日志记录）
    # 用于收集成交明细与订单生命周期
    cerebro.addanalyzer(
        TradeCapture,
        _name="trade_capture"
    )
    cerebro.addanalyzer(
        create_order_capture_analyzer(jq_state),
        _name="order_capture"
    )


def run_strategy(
    cerebro: bt.Cerebro,
    strategy_cls: type,
    strategy_params: Dict[str, Any],
    jq_state: Dict[str, Any] | None = None,
) -> Tuple[bt.Strategy, Iterable[bt.Strategy]]:
    """将策略添加进 Cerebro 并执行，返回主策略实例与原始结果列表
    
    Args:
        cerebro: Backtrader的Cerebro实例
        strategy_cls: 策略类（通常由compile_user_strategy编译生成）
        strategy_params: 策略参数字典
        jq_state: 聚宽状态字典（可选），用于读取运行选项
        
    Returns:
        tuple: (strategy, results)
        - strategy: 回测过程中实际运行的策略对象，便于提取内部自定义变量
        - results: Backtrader原生的策略列表结构（通常只包含一个元素），保持最大兼容性
        
    Notes:
        当前仅支持单策略模式
        
    运行选项:
        - bt_runonce: 是否启用runonce模式（默认True）
        - bt_exactbars: exactbars参数（默认1）
        - flow_debug: 是否输出调试日志（默认False）
    """
    
    # 添加策略到Cerebro
    cerebro.addstrategy(strategy_cls, **strategy_params)
    
    # 读取运行选项：bt_runonce / bt_exactbars
    run_opts = (jq_state or {}).get('options', {}) if isinstance(jq_state, dict) else {}
    runonce = bool(run_opts.get('bt_runonce', True))
    
    try:
        exactbars = int(run_opts.get('bt_exactbars', 1))
    except Exception:
        exactbars = 1
    
    # 输出调试日志（如果启用）
    if (jq_state or {}).get('options', {}).get('flow_debug'):
        try:
            (jq_state or {}).setdefault('log', []).append(
                f"[bt_run] runonce={runonce} exactbars={exactbars}"
            )
        except Exception:
            pass
    
    # 运行回测
    results = cerebro.run(runonce=runonce, exactbars=exactbars)
    
    # 返回首个策略实例（当前仅支持单策略）
    strategy = results[0]
    
    return strategy, results

