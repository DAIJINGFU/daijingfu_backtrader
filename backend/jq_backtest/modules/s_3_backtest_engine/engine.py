"""回测引擎模块 - 协调策略编译、数据加载、选项应用、执行与结果汇总

这个模块是整个回测系统的核心协调器，负责串联所有模块完成完整的回测流程。

主要功能：
- 编译用户策略代码
- 加载历史数据
- 配置回测参数（佣金、滑点等）
- 执行回测
- 收集和汇总结果

整体流程分为以下阶段：
1. 调用 compile_user_strategy 执行用户脚本并识别策略类型
2. 根据 jq_state 预解析 set_option 设置，确定数据加载与成交价模式
3. 通过 prepare_data_sources 读取历史行情，并缓存DataFrame到状态字典
4. 调用 apply_option_settings 配置佣金、滑点、公司行动等选项
5. 注册分析器并运行策略，随后使用 result_pipeline 汇总结果

返回 BacktestResult 数据类，包含回测指标、曲线与交易明细。
"""

import io
import json
import os
import traceback
import re
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import backtrader as bt

from ..s_1_strategy_compile.compiler import compile_user_strategy
from ..s_2_data_loader.data_pipeline import prepare_data_sources
from ..s_4_result_processor.analyzer import compute_metrics_and_curves, collect_trade_and_order_details
from .market_controls import is_stock_paused
from .pipelines import (
    BacktestContext,
    PipelineDependencies,
    PipelineResult,
    BaseBacktestPipeline,
    IntradayPipeline,
    DailyPipeline,
)
from .option_handlers import apply_option_settings
from .trade_limits import setup_global_limit_guards
from ...models import BacktestResult

# 从本模块导入执行器
from .executor import register_default_analyzers, run_strategy


__all__ = [
    "select_pipeline_class",
    "run_backtest",
]


def select_pipeline_class(
    frequency: str, 
    options: Dict[str, Any]
) -> type[BaseBacktestPipeline]:
    """根据频率和选项选择合适的Pipeline类
    
    Args:
        frequency: 回测频率（'daily', 'weekly', 'monthly', 'minute'等）
        options: 回测选项字典，可包含 'enable_daily_pipeline' 等配置
        
    Returns:
        Pipeline类（DailyPipeline 或 IntradayPipeline）
        
    Notes:
        - 当frequency为'daily'/'weekly'/'monthly'且未禁用时，使用DailyPipeline
        - 其他情况使用IntradayPipeline
        - enable_daily_pipeline 可设为 'auto', 'on', 'off' 等值
    """
    freq = (frequency or '').lower()
    flag = options.get('enable_daily_pipeline', 'auto')

    def _normalize(value: Any) -> str:
        """标准化布尔值和字符串选项"""
        if isinstance(value, str):
            return value.strip().lower()
        if value is True:
            return 'on'
        if value is False:
            return 'off'
        return 'auto'

    normalized = _normalize(flag)

    # 日线/周线/月线频率且未禁用时，使用DailyPipeline
    if freq in {'daily', 'weekly', 'monthly'}:
        if normalized in {'auto', 'on', 'true', '1', 'enable', 'enabled'}:
            return DailyPipeline
        if normalized in {'daily'}:
            return DailyPipeline
    
    # 分钟级或显式禁用时，使用IntradayPipeline
    if normalized in {'intraday', 'off', 'false', '0', 'disable', 'disabled'}:
        return IntradayPipeline
    
    # 默认使用IntradayPipeline
    return IntradayPipeline


def run_backtest(
    symbol: str,
    start: str,
    end: str,
    cash: float,
    strategy_code: str,
    strategy_params: Optional[Dict[str, Any]] = None,
    benchmark_symbol: Optional[str] = None,
    frequency: str = 'daily',
    adjust_type: str = 'auto',
    datadir: str = 'data',
) -> BacktestResult:
    """执行完整的回测流程
    
    Args:
        symbol: 股票代码（如 '000001.XSHE' 或 '000001'）
        start: 回测开始日期（'YYYY-MM-DD'）
        end: 回测结束日期（'YYYY-MM-DD'）
        cash: 初始资金
        strategy_code: 用户策略代码（Python字符串）
        strategy_params: 策略参数字典（可选）
        benchmark_symbol: 基准对比标的（可选）
        frequency: 回测频率（'daily', 'minute'等，默认'daily'）
        adjust_type: 复权类型（'auto', 'qfq', 'hfq', 'raw'，默认'auto'）
        datadir: 数据目录（默认'data'）
        
    Returns:
        BacktestResult对象，包含：
        - metrics: 回测指标字典
        - equity_curve: 权益曲线
        - daily_returns: 日收益率序列
        - trades: 交易记录列表
        - orders: 订单记录列表
        - log: 日志信息
        等
        
    Raises:
        不会抛出异常，所有错误都会被捕获并返回在BacktestResult中
        
    Examples:
        >>> code = '''
        ... def initialize(context):
        ...     g.security = '000001.XSHE'
        ... 
        ... def handle_data(context, data):
        ...     order_value(g.security, 10000)
        ... '''
        >>> result = run_backtest(
        ...     '000001.XSHE', 
        ...     '2024-01-01', 
        ...     '2024-12-31',
        ...     100000, 
        ...     code
        ... )
        >>> print(result.metrics['total_return'])
    """
    log_buffer = io.StringIO()
    
    try:
        # ===== 第1步：编译策略 & 初始化 Cerebro =====
        StrategyCls, jq_state = compile_user_strategy(strategy_code)
        
        # 记录用户开始日期
        jq_state['user_start'] = start
        
        # 预扫描用户代码：提前检测set_option调用
        # 因为initialize在数据加载之后才执行，若用户在initialize内才set_option
        # 会错过"选raw文件"阶段，这里用正则提前检测并预置option
        try:
            # use_real_price选项检测
            if 'use_real_price' not in jq_state.get('options', {}):
                m_use = re.search(
                    r"set_option\(\s*['\"]use_real_price['\"]\s*,\s*(True|False|true|false|1|0)\s*\)", 
                    strategy_code
                )
                if m_use:
                    raw_val = m_use.group(1)
                    val = True if raw_val in ('True', 'true', '1') else False
                    jq_state['options']['use_real_price'] = val
                    jq_state['log'].append(
                        f"[preparse] detected use_real_price={val} (token={raw_val}) in source code"
                    )
            
            # adjust_type选项检测
            if 'adjust_type' not in jq_state.get('options', {}):
                m_adj = re.search(
                    r"set_option\(\s*['\"]adjust_type['\"]\s*,\s*['\"](raw|qfq|hfq|auto)['\"]",
                    strategy_code,
                    re.IGNORECASE
                )
                if m_adj:
                    jq_state['options']['adjust_type'] = m_adj.group(1).lower()
                    jq_state['log'].append(
                        f"[preparse] detected adjust_type={m_adj.group(1).lower()} in source code"
                    )
        except Exception:
            pass
        
        # 若调用方传入adjust_type/frequency且用户未在策略set_option指定，则采用传入值
        if 'adjust_type' not in jq_state.get('options', {}):
            jq_state['options']['adjust_type'] = adjust_type
        jq_state['options']['api_frequency'] = frequency
        
        # 创建cerebro（根据成交价类型决定cheat_on_open）
        fill_price_opt = str(jq_state.get('options', {}).get('fill_price', 'open')).lower()
        try:
            cerebro = bt.Cerebro(cheat_on_open=(fill_price_opt == 'open'))
            if jq_state.get('options', {}).get('flow_debug'):
                jq_state['log'].append(
                    f"[exec_mode] fill_price={fill_price_opt} cheat_on_open={fill_price_opt == 'open'}"
                )
        except Exception:
            cerebro = bt.Cerebro()
            if jq_state.get('options', {}).get('flow_debug'):
                jq_state['log'].append(
                    f"[exec_mode] fill_price={fill_price_opt} cheat_on_open=unsupported"
                )
        
        cerebro.broker.setcash(cash)
        
        # 全局买卖限价拦截（支持blocked_orders记录）
        try:
            setup_global_limit_guards(jq_state)
        except Exception:
            pass
        
        # ===== 第2步：通过pipeline管线执行完整流程 =====
        effective_params = strategy_params or {}
        
        # 构造依赖注入对象
        deps = PipelineDependencies(
            prepare_data_sources=prepare_data_sources,
            apply_option_settings=apply_option_settings,
            register_default_analyzers=register_default_analyzers,
            run_strategy=run_strategy,
            compute_metrics_and_curves=compute_metrics_and_curves,
            collect_trade_and_order_details=collect_trade_and_order_details,
        )
        
        # 构造pipeline上下文
        pipeline_ctx = BacktestContext(
            symbol_input=symbol,
            start=start,
            end=end,
            cash=cash,
            frequency=frequency,
            adjust_type=adjust_type,
            strategy_code=strategy_code,
            benchmark_symbol=benchmark_symbol,
            strategy_params=effective_params,
            jq_state=jq_state,
            cerebro=cerebro,
            strategy_cls=StrategyCls,
        )
        
        # 选择并创建pipeline
        pipeline_cls = select_pipeline_class(frequency, jq_state.get('options', {}))
        pipeline = pipeline_cls(pipeline_ctx, deps)
        
        # 执行pipeline
        pipeline_result: PipelineResult = pipeline.run()
        
        # 提取调试信息
        metrics_debug = pipeline_ctx.jq_state.get("metrics_debug")
        diagnostics = pipeline_ctx.jq_state.get("diagnostics")
        result_sections = pipeline_ctx.jq_state.get("result_sections")
        
        # ===== 第3步：构造并返回结果 =====
        return BacktestResult(
            metrics=pipeline_result.metrics,
            equity_curve=pipeline_result.equity_curve,
            daily_returns=pipeline_result.daily_returns,
            daily_pnl=pipeline_result.daily_pnl,
            daily_turnover=pipeline_result.daily_turnover,
            benchmark_curve=pipeline_result.benchmark_curve,
            excess_curve=pipeline_result.excess_curve,
            trades=pipeline_result.trades,
            orders=pipeline_result.orders,
            blocked_orders=pipeline_result.blocked_orders,
            log=log_buffer.getvalue(),
            jq_records=pipeline_result.jq_records,
            jq_logs=pipeline_result.jq_logs,
            metrics_debug=metrics_debug,
            diagnostics=diagnostics,
            result_sections=result_sections,
        )
        
    except Exception:
        # 捕获所有异常，返回错误结果
        tb = traceback.format_exc()
        return BacktestResult(
            metrics={'error': True},
            equity_curve=[],
            daily_returns=[],
            daily_pnl=[],
            daily_turnover=[],
            benchmark_curve=[],
            excess_curve=[],
            trades=[],
            orders=[],
            blocked_orders=[],
            log=tb,
            jq_records=None,
            jq_logs=None,
        )


# ===== 测试代码 =====
if __name__ == '__main__':
    # 简单自测
    code = """
import backtrader as bt

class UserStrategy(bt.Strategy):
    def next(self):
        if not self.position:
            self.buy(size=10)
        elif len(self) > 5:
            self.sell()
"""
    
    # 注意：需要先准备 data/sample.csv
    res = run_backtest(
        'sample',
        '2025-01-01',
        '2025-03-01',
        100000,
        code,
        benchmark_symbol='sample'
    )
    print(json.dumps(asdict(res), ensure_ascii=False, indent=2))

