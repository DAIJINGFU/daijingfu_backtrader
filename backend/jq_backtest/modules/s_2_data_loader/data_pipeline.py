"""数据加载管线抽象：按频率拆分日线与分线加载逻辑。"""

from __future__ import annotations

import math as _math
import re
from typing import Any, Dict, Iterable, List, MutableMapping, Optional, Sequence, Tuple

import backtrader as bt
import pandas as pd

from . import csv_loader as _dl


class BaseDataLoader:
    """统一管理标的解析、预热区间计算与行情加载的基础类。"""

    def __init__(
        self,
        cerebro: bt.Cerebro,
        jq_state: MutableMapping[str, Any],
        symbol_input: Sequence[str] | str,
        start: str,
        end: str,
        frequency: str,
        adjust_type: str,
        strategy_code: str,
        benchmark_symbol: Optional[str],
        warmup_start: Optional[str] = None,
    ) -> None:
        self.cerebro = cerebro
        self.jq_state = jq_state
        self.symbol_input = symbol_input
        self.start = start
        self.end = end
        self.frequency = frequency.lower()
        self.adjust_type = adjust_type
        self.strategy_code = strategy_code
        self.benchmark_symbol = benchmark_symbol
        self.explicit_warmup_start = warmup_start

        self.options = self.jq_state.setdefault("options", {})
        self.log = self.jq_state.setdefault("log", [])
        self.symbol_file_map = self.jq_state.setdefault("symbol_file_map", {})
        self.history_df_map = self.jq_state.setdefault("history_df_map", {})

        self.base_symbols: List[str] = []

    # ------------------------------------------------------------------
    # 公共操作
    # ------------------------------------------------------------------

    def run(self) -> Tuple[List[str], Optional[str]]:
        self.base_symbols = self._normalize_symbols()
        warmup_start = self._resolve_warmup_start()
        final_adjust = self.options.get("adjust_type", self.adjust_type)
        use_real_price_flag = self.options.get("use_real_price")

        for idx, base in enumerate(self.base_symbols):
            self._load_single_symbol(
                base=base,
                warmup_start=warmup_start,
                adjust=final_adjust,
                use_real_price=use_real_price_flag,
                is_primary=(idx == 0),
            )

        benchmark = self.benchmark_symbol or self.jq_state.get("benchmark")
        return self.base_symbols, benchmark

    # ------------------------------------------------------------------
    # 具体实现
    # ------------------------------------------------------------------

    def _normalize_symbols(self) -> List[str]:
        symbols: List[str] = []
        g_sec = getattr(self.jq_state.get("g"), "security", None)
        if g_sec:
            if isinstance(g_sec, (list, tuple, set)):
                symbols = [str(s).strip() for s in g_sec if str(s).strip()]
            elif isinstance(g_sec, str):
                symbols = [g_sec.strip()]

        if not symbols:
            if isinstance(self.symbol_input, str):
                symbols = [s.strip() for s in self.symbol_input.split(",") if s.strip()]
            elif isinstance(self.symbol_input, Iterable):
                symbols = [str(s).strip() for s in self.symbol_input if str(s).strip()]

        if not symbols:
            raise ValueError("未指定任何标的: 请在策略 g.security 或 表单 symbol 提供至少一个")

        def _base_code(code: str) -> str:
            cleaned = code.replace(".XSHE", "").replace(".XSHG", "").replace(".xshe", "").replace(".xshg", "")
            return re.split(r"[_ ]+", cleaned)[0]

        base_symbols = list(dict.fromkeys([_base_code(s) for s in symbols]))
        self.jq_state["primary_symbol"] = base_symbols[0]
        self.log.append(
            f"[symbol_unified] input={symbols} base={base_symbols} freq={self.frequency} adjust={self.options.get('adjust_type')}"
        )
        return base_symbols

    def _resolve_warmup_start(self) -> str:
        if self.explicit_warmup_start:
            return self.explicit_warmup_start

        lookback_days = self._compute_lookback_days()
        warmup_start = (pd.to_datetime(self.start) - pd.Timedelta(days=lookback_days)).date().isoformat()
        return warmup_start

    def _compute_lookback_days(self) -> int:
        lookback_days = 250
        user_set = False

        lb = self.options.get("history_lookback_days")
        if isinstance(lb, (int, float)) and lb >= 0:
            lookback_days = int(lb)
            user_set = True

        lookback_days = self._adjust_lookback_for_frequency(lookback_days, user_set)

        if not user_set and self._should_auto_expand():
            lookback_days = self._auto_expand_lookback(lookback_days)

        return max(0, int(lookback_days))

    def _adjust_lookback_for_frequency(self, lookback_days: int, user_set: bool) -> int:
        return lookback_days

    def _should_auto_expand(self) -> bool:
        try:
            return bool(self.options.get("jq_auto_history_preload", True))
        except Exception:
            return True

    def _auto_expand_lookback(self, lookback_days: int) -> int:
        try:
            periods: List[int] = []
            for m in re.finditer(r"period\s*=\s*(\d{1,4})", self.strategy_code):
                periods.append(int(m.group(1)))
            for m in re.finditer(
                r"\b(SMA|EMA|MA|ATR|RSI|WMA|TRIMA|KAMA|ADX|CCI)\s*\(\s*[^,\n]*?(\d{1,4})",
                self.strategy_code,
                re.IGNORECASE,
            ):
                try:
                    periods.append(int(m.group(2)))
                except Exception:
                    continue
            periods = [p for p in periods if p >= 3]
            if not periods:
                self.log.append(f"[auto_history_preload] none_detected use_default={lookback_days}")
                return lookback_days

            max_period = max(periods)
            period_base = self._transform_period_for_frequency(max_period)
            auto_lb = min(period_base * 3, 600)
            if auto_lb > lookback_days:
                lookback_days = auto_lb
            self.log.append(
                f"[auto_history_preload] detected_periods={sorted(set(periods))} max={max_period} lookback_days={lookback_days}"
            )
            return lookback_days
        except Exception as err:
            self.log.append(f"[auto_history_preload_error] {type(err).__name__}:{err}")
            return lookback_days

    def _transform_period_for_frequency(self, period: int) -> int:
        return period

    def _load_single_symbol(
        self,
        base: str,
        warmup_start: str,
        adjust: str,
        use_real_price: Optional[bool],
        is_primary: bool,
    ) -> None:
        try:
            feed_holder: Dict[str, Any] = {}
            feed = _dl.load_bt_feed(
                base,
                warmup_start,
                self.end,
                frequency=self.frequency,
                adjust=adjust,
                prefer_stockdata=True,
                use_real_price=use_real_price,
                out_path_holder=feed_holder,
            )
            self.cerebro.adddata(feed, name=base)

            df_holder: Dict[str, Any] = {}
            full_df = _dl.load_price_dataframe(
                base,
                warmup_start,
                self.end,
                frequency=self.frequency,
                adjust=adjust,
                prefer_stockdata=True,
                use_real_price=use_real_price,
                out_path_holder=df_holder,
            )

            self.history_df_map[base] = full_df
            if is_primary:
                self.jq_state["history_df"] = full_df

            selected_path = df_holder.get("path") or feed_holder.get("path")
            self.symbol_file_map[base] = selected_path or f"{base}:{self.frequency}:{adjust}"
            self.log.append(
                f"[data_loader] code={base} freq={self.frequency} adjust={adjust} use_real_price={use_real_price} rows={len(full_df)} file={selected_path}"
            )
        except Exception as err:
            self.log.append(f"[data_loader_error] code={base} err={type(err).__name__}:{err}")
            raise


class DailyDataLoader(BaseDataLoader):
    """适用于日线 / 周线 / 月线回测的数据加载器。"""

    def _adjust_lookback_for_frequency(self, lookback_days: int, user_set: bool) -> int:
        if user_set:
            return lookback_days
        if self.frequency == "weekly":
            weeks = self.options.get("weekly_default_lookback_weeks", 60) or 60
            return max(lookback_days, int(weeks) * 5)
        if self.frequency == "monthly":
            months = self.options.get("monthly_default_lookback_months", 36) or 36
            return max(lookback_days, int(months) * 21)
        return self.options.get("daily_default_lookback_days", lookback_days)

    def _transform_period_for_frequency(self, period: int) -> int:
        if self.frequency == "weekly":
            return max(1, period * 5)
        if self.frequency == "monthly":
            return max(1, period * 21)
        return period


class IntradayDataLoader(BaseDataLoader):
    """适用于分钟级（分线）回测的数据加载器。"""

    def _adjust_lookback_for_frequency(self, lookback_days: int, user_set: bool) -> int:
        if user_set:
            return lookback_days
        default_lb = self.options.get("minute_default_lookback_days", 10)
        return int(default_lb) or 10

    def _transform_period_for_frequency(self, period: int) -> int:
        bars_per_day = int(self.options.get("minute_bars_per_day", 240)) or 240
        return max(1, _math.ceil(period / bars_per_day))


def prepare_data_sources(
    cerebro: bt.Cerebro,
    jq_state: Dict[str, Any],
    symbol_input: Sequence[str] | str,
    start: str,
    end: str,
    frequency: str,
    adjust_type: str,
    strategy_code: str,
    benchmark_symbol: Optional[str],
    warmup_start: Optional[str] = None,
) -> Tuple[List[str], Optional[str]]:
    """根据频率选择合适的数据加载器并执行加载流程。"""

    freq = (frequency or "").lower()
    if freq in {"daily", "weekly", "monthly"}:
        loader_cls = DailyDataLoader
    else:
        loader_cls = IntradayDataLoader

    loader = loader_cls(
        cerebro=cerebro,
        jq_state=jq_state,
        symbol_input=symbol_input,
        start=start,
        end=end,
        frequency=freq,
        adjust_type=adjust_type,
        strategy_code=strategy_code,
        benchmark_symbol=benchmark_symbol,
        warmup_start=warmup_start,
    )
    return loader.run()


__all__ = [
    "prepare_data_sources",
    "DailyDataLoader",
    "IntradayDataLoader",
]

