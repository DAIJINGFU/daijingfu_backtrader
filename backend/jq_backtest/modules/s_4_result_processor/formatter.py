"""结果格式化模块 - Pipeline-aware result formatter helpers.

提供不同频率管线的结果拆分逻辑：核心返回 payload 保持向后兼容，
同时将调试与诊断信息放入结构化的 section，便于前端与文档消费。

本模块从 backend/app/result_formatter.py 迁移而来，增强了文档和类型提示。

Exports:
    - FormatterPayload: 格式化结果数据类
    - BaseResultFormatter: 基础格式化器
    - DailyResultFormatter: 日线数据格式化器
    - IntradayResultFormatter: 分钟级数据格式化器
    - build_formatter: 工厂函数，根据频率构建对应格式化器
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from backend.modules.s_3_backtest_engine.pipelines import PipelineResult


@dataclass
class FormatterPayload:
    """格式化后的结果数据包装类
    
    Attributes:
        core: 核心业务数据（指标、曲线、交易记录等）
        diagnostics: 诊断信息（性能统计、调试信息等）
        extras: 扩展信息（基准、因子分析等）
    """
    core: Dict[str, Any]
    diagnostics: Dict[str, Any]
    extras: Dict[str, Any]


class BaseResultFormatter:
    """默认格式化逻辑，适用于多数日线场景。
    
    此类定义了基础的结果格式化流程，将回测结果拆分为：
    1. 核心数据区：指标、曲线、交易记录
    2. 诊断信息区：调试信息、性能统计
    3. 扩展信息区：额外的分析数据
    
    子类可以重写 format() 方法来定制不同频率的格式化逻辑。
    """

    pipeline: str = "base"

    def format(self, result: "PipelineResult", jq_state: Dict[str, Any]) -> FormatterPayload:
        """格式化回测结果
        
        Args:
            result: Pipeline执行后的原始结果对象
            jq_state: 聚宽状态字典，包含配置、日志等信息
            
        Returns:
            FormatterPayload: 结构化的格式化结果
        """
        metrics_debug = jq_state.get("metrics_debug", {})
        
        # 核心数据：业务指标和曲线
        sections: Dict[str, Any] = {
            "metrics": result.metrics,
            "curves": {
                "equity": result.equity_curve,
                "daily_returns": result.daily_returns,
                "daily_pnl": result.daily_pnl,
                "benchmark": result.benchmark_curve,
                "excess": result.excess_curve,
            },
            "trades": {
                "trades": result.trades,
                "orders": result.orders,
                "blocked": result.blocked_orders,
                "daily_turnover": result.daily_turnover,
            },
            "jq_records": result.jq_records,
            "jq_logs": result.jq_logs,
        }
        
        # 诊断信息：调试和性能数据
        diagnostics = {
            "pipeline": self.pipeline,
            "metrics_debug": metrics_debug,
            "jq_log_size": len(result.jq_logs),
            "symbol_count": len(result.metrics.get("symbols_used", [])) if isinstance(result.metrics, dict) else None,
            "runtime_diagnostics": jq_state.get("diagnostics"),
            "protocol_version": 1,
        }
        
        # 扩展信息：额外的分析数据
        extras = {
            "benchmark": result.metrics.get("benchmark_symbol_used") if isinstance(result.metrics, dict) else None,
        }
        
        return FormatterPayload(core=sections, diagnostics=diagnostics, extras=extras)


class DailyResultFormatter(BaseResultFormatter):
    """日线数据格式化器
    
    专门用于日线频率回测结果的格式化，添加了日线特有的诊断信息：
    - 频率标识
    - 因子分析结果
    - 股票池信息
    """

    pipeline = "daily"

    def format(self, result: "PipelineResult", jq_state: Dict[str, Any]) -> FormatterPayload:
        """格式化日线回测结果
        
        在基础格式化的基础上，添加日线特有的诊断和扩展信息。
        
        Args:
            result: Pipeline执行后的原始结果对象
            jq_state: 聚宽状态字典
            
        Returns:
            FormatterPayload: 包含日线特有信息的格式化结果
        """
        payload = super().format(result, jq_state)
        
        # 添加日线特有的诊断信息
        payload.diagnostics.update(
            {
                "frequency": jq_state.get("frequency", "daily"),
                "result_type": "daily",
            }
        )
        
        # 添加日线特有的扩展信息
        payload.extras.setdefault("sections", {})
        payload.extras["sections"].update(
            {
                "factor_diagnostics": jq_state.get("factor_analysis"),
                "stock_pool": jq_state.get("stock_pool_summary"),
            }
        )
        
        return payload


class IntradayResultFormatter(BaseResultFormatter):
    """分钟级数据格式化器
    
    专门用于分钟级频率回测结果的格式化，添加了分钟级特有的诊断信息：
    - 分钟数据缓存统计
    - 日内交易日志
    """

    pipeline = "intraday"

    def format(self, result: "PipelineResult", jq_state: Dict[str, Any]) -> FormatterPayload:
        """格式化分钟级回测结果
        
        在基础格式化的基础上，添加分钟级特有的诊断和扩展信息。
        
        Args:
            result: Pipeline执行后的原始结果对象
            jq_state: 聚宽状态字典
            
        Returns:
            FormatterPayload: 包含分钟级特有信息的格式化结果
        """
        payload = super().format(result, jq_state)
        
        minute_cache = jq_state.get("minute_daily_cache")
        
        # 添加分钟级特有的诊断信息
        payload.diagnostics.update(
            {
                "result_type": "intraday",
                "minute_cache_stats": jq_state.get("metrics_debug", {}).get("minute_cache"),
                "cached_symbols": list(minute_cache.keys()) if isinstance(minute_cache, dict) else None,
            }
        )
        
        # 添加分钟级特有的扩展信息
        payload.extras.setdefault("sections", {})
        payload.extras["sections"].update(
            {
                "intraday_logs": [msg for msg in jq_state.get("log", []) if "minute_cache" in str(msg)],
            }
        )
        
        return payload


def build_formatter(frequency: Optional[str]) -> BaseResultFormatter:
    """工厂函数：根据回测频率构建对应的格式化器
    
    Args:
        frequency: 回测频率，如 'daily', '1min', 'minute' 等
        
    Returns:
        BaseResultFormatter: 对应频率的格式化器实例
        
    Examples:
        >>> formatter = build_formatter('daily')
        >>> isinstance(formatter, DailyResultFormatter)
        True
        
        >>> formatter = build_formatter('1min')
        >>> isinstance(formatter, IntradayResultFormatter)
        True
    """
    if frequency in {"1min", "1m", "minute"}:
        return IntradayResultFormatter()
    return DailyResultFormatter()

