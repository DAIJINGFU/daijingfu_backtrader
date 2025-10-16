"""Backtest pipeline abstractions separating shared orchestration logic from
frequency-specific behavior.

The initial implementation provides a base pipeline plus an intraday
implementation that preserves existing semantics. Future daily and hybrid
pipelines can extend from this foundation without touching the core
``run_backtest`` entry point.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math as _math
import re
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import backtrader as bt
import pandas as pd

from ..s_2_data_loader.minute_cache import (
    CacheConfig,
    MinuteAggregationCache,
    aggregate_minute_dataframe,
    build_cache_key,
    default_cache_dir,
    get_source_mtime,
)
from .pipeline_options import ensure_pipeline_defaults
from ..s_4_result_processor.formatter import build_formatter


def _percentile_summary(samples: Sequence[float]) -> Dict[str, Any]:
    """Compute percentile summary (p50/p90/p99) for the provided samples."""

    values = [float(v) for v in samples if v is not None]
    if not values:
        return {"count": 0}

    values.sort()
    count = len(values)

    def _interp(percent: float) -> float:
        if count == 1:
            return values[0]
        rank = percent * (count - 1)
        lower = int(rank)
        upper = min(lower + 1, count - 1)
        fraction = rank - lower
        return values[lower] + (values[upper] - values[lower]) * fraction

    summary: Dict[str, Any] = {
        "count": count,
        "min": round(values[0], 3),
        "max": round(values[-1], 3),
        "avg": round(sum(values) / count, 3),
        "p50": round(_interp(0.50), 3),
        "p90": round(_interp(0.90), 3),
        "p99": round(_interp(0.99), 3),
    }
    return summary


@dataclass
class PipelineResult:
    """Structured output produced by a backtest pipeline run."""

    metrics: Dict[str, Any]
    equity_curve: List[Dict[str, Any]]
    daily_returns: List[Dict[str, Any]]
    daily_pnl: List[Dict[str, Any]]
    benchmark_curve: List[Dict[str, Any]]
    excess_curve: List[Dict[str, Any]]
    trades: List[Any]
    orders: List[Any]
    blocked_orders: List[Any]
    daily_turnover: List[Dict[str, Any]]
    jq_records: Optional[List[Dict[str, Any]]]
    jq_logs: List[str]


@dataclass
class BacktestContext:
    """Runtime context shared across pipeline stages."""

    symbol_input: Sequence[str] | str
    start: str
    end: str
    cash: float
    frequency: str
    adjust_type: str
    strategy_code: str
    benchmark_symbol: Optional[str]
    strategy_params: Dict[str, Any]
    jq_state: Dict[str, Any]
    cerebro: bt.Cerebro
    strategy_cls: type
    symbols: List[str] = field(default_factory=list)
    strat: Optional[bt.Strategy] = None
    results: Optional[Iterable[bt.Strategy]] = None


@dataclass
class PipelineDependencies:
    """Injectable collaborators used by pipelines to perform work."""

    prepare_data_sources: Callable[[
        bt.Cerebro,
        Dict[str, Any],
        Sequence[str] | str,
        str,
        str,
        str,
        str,
        str,
        Optional[str],
    ], Tuple[List[str], Optional[str]]]
    apply_option_settings: Callable[[bt.Cerebro, Dict[str, Any]], None]
    register_default_analyzers: Callable[[bt.Cerebro, Dict[str, Any]], None]
    run_strategy: Callable[[bt.Cerebro, type, Dict[str, Any], Dict[str, Any]], Tuple[bt.Strategy, Iterable[bt.Strategy]]]
    compute_metrics_and_curves: Callable[[
        bt.Cerebro,
        bt.Strategy,
        Dict[str, Any],
        str,
        str,
        float,
        str,
        Optional[str],
        Iterable[str],
    ], Tuple[
        Dict[str, Any],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
    ]]
    collect_trade_and_order_details: Callable[[
        bt.Strategy,
        Dict[str, Any],
        str,
    ], Tuple[
        List[Any],
        List[Any],
        List[Any],
        List[Dict[str, Any]],
    Optional[List[Dict[str, Any]]],
        List[str],
    ]]


class BaseBacktestPipeline:
    """Default orchestration shared by all backtest pipelines."""

    def __init__(self, context: BacktestContext, deps: PipelineDependencies) -> None:
        self.ctx = context
        self.deps = deps
        self.ctx.jq_state.setdefault("log", []).append(
            f"[pipeline] using={self.__class__.__name__} freq={self.ctx.frequency}"
        )

    # --- Orchestration -------------------------------------------------

    def run(self) -> PipelineResult:
        self.load_data()
        self.configure_execution()
        self.execute_strategy()
        return self.collect_results()

    # --- Hooks for subclasses -----------------------------------------

    def load_data(self) -> None:
        warmup_start = self.determine_warmup_start()
        symbols, benchmark = self.deps.prepare_data_sources(
            cerebro=self.ctx.cerebro,
            jq_state=self.ctx.jq_state,
            symbol_input=self.ctx.symbol_input,
            start=self.ctx.start,
            end=self.ctx.end,
            frequency=self.ctx.frequency,
            adjust_type=self.ctx.adjust_type,
            strategy_code=self.ctx.strategy_code,
            benchmark_symbol=self.ctx.benchmark_symbol,
            warmup_start=warmup_start,
        )
        self.ctx.symbols = symbols
        self.ctx.benchmark_symbol = benchmark
        self.post_load()

    def configure_execution(self) -> None:
        self.deps.apply_option_settings(self.ctx.cerebro, self.ctx.jq_state)
        self.deps.register_default_analyzers(self.ctx.cerebro, self.ctx.jq_state)

    def execute_strategy(self) -> None:
        strat, results = self.deps.run_strategy(
            self.ctx.cerebro,
            self.ctx.strategy_cls,
            self.ctx.strategy_params,
            jq_state=self.ctx.jq_state,
        )
        self.ctx.strat = strat
        self.ctx.results = results

    def collect_results(self) -> PipelineResult:
        assert self.ctx.strat is not None, "strategy run must populate ctx.strat"

        metrics, equity_curve, daily_returns, daily_pnl, benchmark_curve, excess_curve = (
            self.deps.compute_metrics_and_curves(
                cerebro=self.ctx.cerebro,
                strat=self.ctx.strat,
                jq_state=self.ctx.jq_state,
                start=self.ctx.start,
                end=self.ctx.end,
                cash=self.ctx.cash,
                frequency=self.ctx.frequency,
                benchmark_symbol=self.ctx.benchmark_symbol,
                symbols=self.ctx.symbols,
            )
        )

        trades, orders, blocked_orders, daily_turnover, jq_records, jq_logs = (
            self.deps.collect_trade_and_order_details(
                strat=self.ctx.strat,
                jq_state=self.ctx.jq_state,
                start=self.ctx.start,
            )
        )

        result = PipelineResult(
            metrics=metrics,
            equity_curve=equity_curve,
            daily_returns=daily_returns,
            daily_pnl=daily_pnl,
            benchmark_curve=benchmark_curve,
            excess_curve=excess_curve,
            trades=trades,
            orders=orders,
            blocked_orders=blocked_orders,
            daily_turnover=daily_turnover,
            jq_records=jq_records,
            jq_logs=jq_logs,
        )

        formatter = build_formatter(self.ctx.frequency)
        formatted = formatter.format(result, self.ctx.jq_state)
        self.ctx.jq_state["result_sections"] = {
            "core": formatted.core,
            "diagnostics": formatted.diagnostics,
            "extras": formatted.extras,
        }
        return result

    # --- Helpers ------------------------------------------------------

    def determine_warmup_start(self) -> str:
        lookback_days = self.compute_lookback_days()
        try:
            warmup_start = (pd.to_datetime(self.ctx.start) - pd.Timedelta(days=lookback_days)).date().isoformat()
        except Exception:
            warmup_start = self.ctx.start
        self.ctx.jq_state.setdefault("log", []).append(
            f"[pipeline_warmup] freq={self.ctx.frequency} lookback_days={lookback_days} warmup_start={warmup_start}"
        )
        return warmup_start

    def compute_lookback_days(self) -> int:
        options = self.ctx.jq_state.setdefault("options", {})
        lookback_days = 250
        self._user_set_history = False
        lb = options.get("history_lookback_days")
        if isinstance(lb, (int, float)) and lb >= 0:
            lookback_days = int(lb)
            self._user_set_history = True

        lookback_days = self.adjust_lookback_for_frequency(lookback_days, self._user_set_history)

        if self.should_auto_expand():
            lookback_days = self.auto_expand_lookback(lookback_days)

        return max(0, int(lookback_days))

    def adjust_lookback_for_frequency(self, lookback_days: int, user_set: bool) -> int:
        return lookback_days

    def should_auto_expand(self) -> bool:
        if getattr(self, "_user_set_history", False):
            return False
        try:
            return bool(self.ctx.jq_state.get("options", {}).get("jq_auto_history_preload", True))
        except Exception:
            return True

    def auto_expand_lookback(self, lookback_days: int) -> int:
        try:
            periods: List[int] = []
            for m in re.finditer(r"period\s*=\s*(\d{1,4})", self.ctx.strategy_code):
                periods.append(int(m.group(1)))
            for m in re.finditer(
                r"\b(SMA|EMA|MA|ATR|RSI|WMA|TRIMA|KAMA|ADX|CCI)\s*\(\s*[^,\n]*?(\d{1,4})",
                self.ctx.strategy_code,
                re.IGNORECASE,
            ):
                try:
                    periods.append(int(m.group(2)))
                except Exception:
                    continue
            periods = [p for p in periods if p >= 3]
            if not periods:
                self.ctx.jq_state.setdefault("log", []).append(
                    f"[auto_history_preload] none_detected use_default={lookback_days}"
                )
                return lookback_days

            max_period = max(periods)
            period_base = self.transform_period_for_frequency(max_period)
            auto_lb = min(period_base * 3, 600)
            if auto_lb > lookback_days:
                lookback_days = auto_lb
            self.ctx.jq_state.setdefault("log", []).append(
                f"[auto_history_preload] detected_periods={sorted(set(periods))} max={max_period} lookback_days={lookback_days}"
            )
            return lookback_days
        except Exception as err:
            self.ctx.jq_state.setdefault("log", []).append(
                f"[auto_history_preload_error] {type(err).__name__}:{err}"
            )
            return lookback_days

    def transform_period_for_frequency(self, period: int) -> int:
        return period

    def post_load(self) -> None:
        """Hook for subclasses once数据加载结束。"""
        return


class IntradayPipeline(BaseBacktestPipeline):
    """Current default pipeline covering both minute and legacy shared path."""

    def load_data(self) -> None:
        super().load_data()
        if self.ctx.frequency == "1min":
            self._prepare_minute_cache()

    def configure_execution(self) -> None:
        self.ensure_intraday_defaults()
        super().configure_execution()

    def adjust_lookback_for_frequency(self, lookback_days: int, user_set: bool) -> int:
        if not user_set and self.ctx.frequency == "1min":
            try:
                default_lb = int(self.ctx.jq_state.get("options", {}).get("minute_default_lookback_days", 10))
            except Exception:
                default_lb = 10
            lookback_days = default_lb or 10
        return lookback_days

    def transform_period_for_frequency(self, period: int) -> int:
        if self.ctx.frequency == "1min":
            try:
                bars_per_day = int(self.ctx.jq_state.get("options", {}).get("minute_bars_per_day", 240))
            except Exception:
                bars_per_day = 240
            bars_per_day = bars_per_day or 240
            return max(1, _math.ceil(period / bars_per_day))
        return period

    def post_load(self) -> None:
        if self.ctx.frequency == "1min" and self.ctx.benchmark_symbol:
            self.ctx.jq_state.setdefault("log", []).append("[benchmark_notice] 1min 回测暂使用日线基准对齐")
        if self.ctx.frequency == "1min":
            self.ctx.jq_state.setdefault("minute_daily_cache", {})

    def ensure_intraday_defaults(self) -> None:
        ensure_pipeline_defaults(self.ctx.jq_state, "intraday", self.ctx.frequency)

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _prepare_minute_cache(self) -> None:
        jq_state = self.ctx.jq_state
        history_map: Dict[str, pd.DataFrame] = jq_state.get("history_df_map") or {}
        if not history_map:
            return

        options = jq_state.setdefault("options", {})
        persist = bool(options.get("persist_minute_agg", False))
        logger = lambda msg: jq_state.setdefault("log", []).append(msg)
        cache_dir_opt = options.get("minute_cache_dir")
        if cache_dir_opt:
            try:
                cache_dir = Path(str(cache_dir_opt)).expanduser()
            except Exception:
                logger(f"[minute_cache] invalid_cache_dir value={cache_dir_opt!r}, fallback=default")
                cache_dir = default_cache_dir()
        else:
            cache_dir = default_cache_dir()
        cache = MinuteAggregationCache(CacheConfig(persist=persist, cache_dir=cache_dir, log=logger))

        minute_cache = jq_state.setdefault("minute_daily_cache", {})
        metrics_debug = jq_state.setdefault("metrics_debug", {})
        diagnostics = jq_state.setdefault("diagnostics", {})
        mc_metrics = {
            "hits": 0,
            "misses": 0,
            "mismatches": 0,
            "builds": 0,
            "saves": 0,
            "errors": 0,
            "records": [],
        }
        metrics_debug["minute_cache"] = mc_metrics
        adjust = options.get("adjust_type", self.ctx.adjust_type)
        use_real_price = options.get("use_real_price")
        symbol_paths = jq_state.get("symbol_file_map", {})

        for symbol in self.ctx.symbols:
            df = history_map.get(symbol)
            if df is None or df.empty or "datetime" not in df.columns:
                continue
            cache_key = build_cache_key(symbol, adjust, use_real_price)
            source_path = symbol_paths.get(symbol)
            source_mtime = get_source_mtime(source_path)

            load_start = perf_counter()
            aggregated = cache.load(cache_key, source_mtime)
            load_ms = round((perf_counter() - load_start) * 1000, 3)
            load_status = cache.last_status or "unknown"
            record: Dict[str, Any] = {
                "symbol": symbol,
                "cache_key": cache_key,
                "source_mtime": source_mtime,
                "load_status": load_status,
                "load_ms": load_ms,
                "load_rows": cache.last_rows,
            }
            if cache.last_error:
                record["load_error"] = cache.last_error

            if load_status == "hit":
                mc_metrics["hits"] += 1
            elif load_status == "mismatch":
                mc_metrics["mismatches"] += 1
            elif load_status == "miss":
                mc_metrics["misses"] += 1
            elif load_status in {"meta_error", "load_error"}:
                mc_metrics["errors"] += 1

            if aggregated is None:
                agg_start = perf_counter()
                aggregated = aggregate_minute_dataframe(df)
                aggregate_ms = round((perf_counter() - agg_start) * 1000, 3)
                record["aggregate_ms"] = aggregate_ms
                record["result_rows"] = len(aggregated)
                mc_metrics["builds"] += 1

                if aggregated.empty:
                    record["save_status"] = "empty"
                    mc_metrics["errors"] += 1
                    mc_metrics["records"].append(record)
                    continue

                jq_state.setdefault("log", []).append(
                    f"[minute_cache] build key={cache_key} rows={len(aggregated)} persist={persist}"
                )
                cache.save(cache_key, aggregated, source_mtime)
                save_status = cache.last_status or ("disabled" if not persist else "saved")
                record["save_status"] = save_status
                if cache.last_error:
                    record["save_error"] = cache.last_error
                if save_status == "saved":
                    mc_metrics["saves"] += 1
                elif save_status != "disabled":
                    mc_metrics["errors"] += 1
            else:
                # 命中缓存时保留当前行数
                record.setdefault("result_rows", cache.last_rows)

            minute_cache[symbol] = aggregated
            if aggregated is not None and "result_rows" not in record:
                record["result_rows"] = len(aggregated)

            mc_metrics["records"].append(record)

        load_samples = [r.get("load_ms") for r in mc_metrics["records"] if r.get("load_ms") is not None]
        aggregate_samples = [r.get("aggregate_ms") for r in mc_metrics["records"] if r.get("aggregate_ms") is not None]
        mc_metrics["timing_ms"] = {
            "load": _percentile_summary(load_samples),
            "aggregate": _percentile_summary(aggregate_samples),
        }
        mc_metrics["error_records"] = [
            {
                "symbol": r["symbol"],
                "load_status": r.get("load_status"),
                "save_status": r.get("save_status"),
                "load_error": r.get("load_error"),
                "save_error": r.get("save_error"),
            }
            for r in mc_metrics["records"]
            if r.get("load_status") in {"meta_error", "load_error"}
            or r.get("save_status") in {"persist_error", "empty"}
        ]
        total_loads = len(mc_metrics["records"])
        total_errors = len(mc_metrics["error_records"])
        total_hits = mc_metrics["hits"]
        total_builds = mc_metrics["builds"]
        total_misses = mc_metrics["misses"]
        total_mismatches = mc_metrics["mismatches"]
        summary = {
            "total_symbols": len(self.ctx.symbols),
            "total_loads": total_loads,
            "hits": total_hits,
            "misses": total_misses,
            "mismatches": total_mismatches,
            "builds": total_builds,
            "errors": total_errors,
        }
        if total_loads:
            summary.update(
                {
                    "hit_rate": round(total_hits / total_loads, 4),
                    "build_ratio": round(total_builds / total_loads, 4),
                    "miss_rate": round(total_misses / total_loads, 4),
                    "mismatch_rate": round(total_mismatches / total_loads, 4),
                }
            )
        mc_metrics["summary"] = summary
        top_anomalies = [
            {
                "symbol": r["symbol"],
                "load_status": r.get("load_status"),
                "save_status": r.get("save_status"),
                "load_ms": r.get("load_ms"),
                "aggregate_ms": r.get("aggregate_ms"),
                "load_error": r.get("load_error"),
                "save_error": r.get("save_error"),
            }
            for r in mc_metrics["records"]
            if r.get("load_status") in {"meta_error", "load_error", "mismatch"}
            or r.get("save_status") in {"persist_error", "empty"}
        ][:10]
        diagnostics["minute_cache"] = {
            "summary": summary,
            "timing_ms": mc_metrics["timing_ms"],
            "anomalies": top_anomalies,
        }
        if summary.get("errors"):
            jq_state.setdefault("log", []).append(
                f"[minute_cache_diag] errors={summary['errors']} hits={total_hits} misses={total_misses}"
            )


class DailyPipeline(BaseBacktestPipeline):
    """Dedicated pipeline for日线/周线/月线回测路径。"""

    def configure_execution(self) -> None:
        self.ensure_daily_defaults()
        super().configure_execution()

    def adjust_lookback_for_frequency(self, lookback_days: int, user_set: bool) -> int:
        if not user_set and self.ctx.frequency in {"daily", "weekly", "monthly"}:
            try:
                default_lb = int(self.ctx.jq_state.get("options", {}).get("daily_default_lookback_days", 250))
            except Exception:
                default_lb = 250
            if self.ctx.frequency == "weekly":
                try:
                    weeks = int(self.ctx.jq_state.get("options", {}).get("weekly_default_lookback_weeks", 60))
                except Exception:
                    weeks = 60
                default_lb = max(1, weeks * 5)
            elif self.ctx.frequency == "monthly":
                try:
                    months = int(self.ctx.jq_state.get("options", {}).get("monthly_default_lookback_months", 36))
                except Exception:
                    months = 36
                default_lb = max(1, months * 21)  # approximate trading days
            return default_lb or lookback_days
        return lookback_days

    def ensure_daily_defaults(self) -> None:
        ensure_pipeline_defaults(self.ctx.jq_state, "daily", self.ctx.frequency)

    def transform_period_for_frequency(self, period: int) -> int:
        freq = self.ctx.frequency
        if freq == "weekly":
            return max(1, period * 5)
        if freq == "monthly":
            return max(1, period * 21)
        return period


__all__ = [
    "BacktestContext",
    "PipelineDependencies",
    "PipelineResult",
    "BaseBacktestPipeline",
    "IntradayPipeline",
    "DailyPipeline",
]
