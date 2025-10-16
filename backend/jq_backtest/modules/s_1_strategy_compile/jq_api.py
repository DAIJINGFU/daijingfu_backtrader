"""聚宽API函数实现 - 完整的聚宽兼容接口"""

from __future__ import annotations

import datetime as _dt
import math as _math
import re
from typing import Any, Dict, Optional

import pandas as _pd

from backend.modules.s_2_data_loader.minute_cache import aggregate_minute_dataframe
from backend.modules.s_2_data_loader.data_compat import round_to_tick as _round_to_tick
from backend.jq_backtest.models import OrderRecord

from .utils import (
    ensure_list as _ensure_list,
    merge_position as _merge_position,
    normalize_code as _normalize_code,
    parse_date as _parse_date,
    round_to_price_tick as _round_to_price_tick,
    safe_float as _safe_float,
    # Internal helper functions
    ensure_state as _ensure_state,
    resolve_state as _resolve_state,
    resolve_strategy as _resolve_strategy,
    primary_data as _primary_data,
    position_snapshot as _position_snapshot,
    price_context as _price_context,
    normalize_security_key as _normalize_security_key,
    is_null as _is_null,
    to_float as _to_float,
    to_int as _to_int,
    first_valid_value as _first_valid_value,
    extract_datetime_series as _extract_datetime_series,
    resolve_dataframe_for_security as _resolve_dataframe_for_security,
    build_snapshot_for_security as _build_snapshot_for_security,
)

from .jq_models import (
    CurrentSnapshot as _CurrentSnapshot,
    CurrentDataProxy as _CurrentDataProxy,
)


# ═══════════════════════════════════════════════════════════
# 数据获取 API
# ═══════════════════════════════════════════════════════════
# 用于获取历史价格、当前行情、K线数据等
#
# 主要函数：
#   - get_price: 获取历史K线数据（日线/分钟线）
#   - attribute_history: 按天数获取历史数据
#   - history: 批量获取多证券历史数据
#   - get_current_data: 获取当前数据快照
# ═══════════════════════════════════════════════════════════


def get_price(
    security,
    start_date=None,
    end_date=None,
    *,
    frequency: str = "daily",
    fields=None,
    count=None,
    skip_paused: bool = False,
    fq: str = "pre",
    panel: bool = False,
    fill_paused: bool = True,
    jq_state: Optional[Dict[str, Any]] = None,
):
    """获取股票价格数据 - 核心数据接口（当前实现支持日级）。"""

    state = _resolve_state(jq_state, "get_price")

    if frequency.lower() not in ("daily", "d"):
        raise ValueError('当前本地实现仅支持 frequency="daily"')

    secs = _ensure_list(security)
    if not secs:
        if isinstance(fields, str):
            return _pd.Series([], dtype=float)
        return _pd.DataFrame()

    all_possible_fields = [
        "open",
        "close",
        "high",
        "low",
        "volume",
        "money",
        "avg",
        "pre_close",
        "factor",
        "paused",
        "high_limit",
        "low_limit",
    ]

    if fields is None:
        use_fields = ["open", "close", "high", "low", "volume"]
    else:
        use_fields = _ensure_list(fields)

    derived_need = []
    if "money" in use_fields or "avg" in use_fields:
        if "close" not in use_fields:
            derived_need.append("close")
        if "volume" not in use_fields:
            derived_need.append("volume")
    if "pre_close" in use_fields and "close" not in use_fields:
        derived_need.append("close")

    base_field_set = set(use_fields + derived_need)
    base_field_set.intersection_update(all_possible_fields)

    cur_bt_date = None
    cur_dt_raw = state.get("current_dt")
    if cur_dt_raw:
        try:
            cur_bt_date = _pd.to_datetime(cur_dt_raw).date()
        except Exception:
            cur_bt_date = None

    end_d = _parse_date(end_date)
    if end_d is None and cur_bt_date is not None:
        end_d = cur_bt_date - _dt.timedelta(days=1)
    start_d = _parse_date(start_date)

    if count is not None and start_d is not None:
        raise ValueError("count 与 start_date 不能同时指定")
    if count is None and start_d is None:
        count = 1

    per_sec_frames: Dict[str, _pd.DataFrame] = {}
    hist_map = state.get("history_df_map") or {}
    global_df = state.get("history_df")

    for sec in secs:
        base = str(sec).split(".")[0]
        df_full = hist_map.get(base)
        if df_full is None:
            for key, value in hist_map.items():
                if str(key).startswith(base):
                    df_full = value
                    break
        if df_full is None and isinstance(global_df, _pd.DataFrame):
            df_full = global_df

        if df_full is None or "datetime" not in df_full.columns:
            per_sec_frames[sec] = _pd.DataFrame(columns=use_fields)
            continue

        working = df_full[[c for c in ["datetime", "open", "close", "high", "low", "volume"] if c in df_full.columns]].copy()
        working["datetime"] = _pd.to_datetime(working["datetime"], errors="coerce")
        working = working.dropna(subset=["datetime"])
        working["date"] = working["datetime"].dt.date

        if not working.empty and working["date"].nunique() < len(working):
            cache = state.setdefault("minute_daily_cache", {})
            cache_key = base
            cached_daily = cache.get(cache_key)
            if cached_daily is None:
                aggregated = aggregate_minute_dataframe(df_full)
                cache[cache_key] = aggregated
                try:
                    log = state.setdefault("log", [])
                    if not state.get("_minute_source_aggregated_logged"):
                        state["_minute_source_aggregated_logged"] = True
                        log.append("[minute_source_aggregate] detected minute-level history -> aggregated to daily for get_price/attribute_history")
                    log.append(f"[minute_daily_cache] build sec={cache_key} rows={len(aggregated)}")
                except Exception:
                    pass
                working = aggregated.copy()
            else:
                working = cached_daily.copy()
        else:
            working = working.sort_values("datetime")

        if working.empty:
            per_sec_frames[sec] = _pd.DataFrame(columns=use_fields)
            continue

        if cur_bt_date is not None:
            working = working[working["date"] < cur_bt_date]
        if working.empty:
            per_sec_frames[sec] = _pd.DataFrame(columns=use_fields)
            continue

        if count is not None:
            if end_d is not None:
                working = working[working["date"] <= end_d]
            working = working.tail(int(count))
        else:
            if start_d is not None:
                working = working[working["date"] >= start_d]
            if end_d is not None:
                working = working[working["date"] <= end_d]

        if working.empty:
            per_sec_frames[sec] = _pd.DataFrame(columns=use_fields)
            continue

        working = working.sort_values("date")
        if "_synthetic" not in working.columns:
            working["_synthetic"] = 0

        if "money" in base_field_set and "money" not in working.columns:
            try:
                working["money"] = working["close"] * working.get("volume", 0)
            except Exception:
                working["money"] = _pd.NA
        if "avg" in base_field_set and "avg" not in working.columns:
            try:
                vol = working.get("volume")
                working["avg"] = (working["close"] * vol) / vol.replace(0, _pd.NA)
            except Exception:
                working["avg"] = _pd.NA
        if "pre_close" in base_field_set:
            working["pre_close"] = working["close"].shift(1)
        if "factor" in base_field_set and "factor" not in working.columns:
            working["factor"] = 1.0
        if "paused" in base_field_set:
            working["paused"] = (working.get("volume", 0) == 0).astype(int)

        if {"high_limit", "low_limit"} & base_field_set:
            try:
                limit_pct = float(state.get("options", {}).get("limit_pct", 0.1) or 0.1)
            except Exception:
                limit_pct = 0.1
            ref_pc = working.get("pre_close") if "pre_close" in working.columns else working["close"].shift(1)
            tick = float(state.get("options", {}).get("price_tick", 0.01) or 0.01)
            working["high_limit"] = ref_pc.map(lambda x: _round_to_price_tick(x * (1 + limit_pct), tick) if _pd.notnull(x) else x)
            working["low_limit"] = ref_pc.map(lambda x: _round_to_price_tick(x * (1 - limit_pct), tick) if _pd.notnull(x) else x)

        if "paused" in working.columns:
            if skip_paused:
                working = working[working["paused"] == 0]
            elif not fill_paused:
                paused_mask = working["paused"] == 1
                if paused_mask.any():
                    for col in list(working.columns):
                        if col not in ("datetime", "date", "paused"):
                            working.loc[paused_mask, col] = _pd.NA

        out_cols = [col for col in use_fields if col in working.columns]
        result = working[["date", *out_cols]].copy()
        result.set_index("date", inplace=True)
        per_sec_frames[sec] = result

    if len(secs) == 1:
        single = per_sec_frames[secs[0]]
        single.index.name = None
        if isinstance(fields, str):
            series = single[fields] if fields in single.columns else _pd.Series([], dtype=float)
            series.index.name = None
            return series
        return single

    if panel:
        class PanelEmu:
            def __init__(self, data_map):
                all_dates = sorted({d for df in data_map.values() for d in df.index})
                self._secs = list(data_map.keys())
                self._cube = {}
                fields_local = set()
                for field in use_fields:
                    mat = _pd.DataFrame(index=all_dates, columns=self._secs, dtype=float)
                    for sec_key, df in data_map.items():
                        if field in df.columns:
                            mat.loc[df.index, sec_key] = df[field]
                    self._cube[field] = mat
                    fields_local.add(field)
                self._fields = list(fields_local)

            def __getitem__(self, item):
                return self._cube.get(item, _pd.DataFrame())

            @property
            def fields(self):
                return list(self._fields)

            @property
            def symbols(self):
                return list(self._secs)

        return PanelEmu(per_sec_frames)

    return per_sec_frames

def attribute_history(
    security,
    count: int,
    unit: str = "1d",
    fields=None,
    skip_paused: bool = True,
    df: bool = True,
    fq: str = "pre",
    *,
    jq_state: Optional[Dict[str, Any]] = None,
):
    """获取历史数据 - 按天数获取（仅支持日级）。"""

    state = _resolve_state(jq_state, "attribute_history")

    if unit.lower() not in ("1d", "day", "d"):
        raise ValueError("attribute_history 目前仅支持日级 unit=1d")

    if count <= 0:
        return _pd.DataFrame() if df else {}

    options = state.get("options", {})
    include_current = bool(options.get("attribute_history_include_current", False))

    if fields is None:
        fields_list = ["open", "close", "high", "low", "volume", "money"]
    else:
        fields_list = _ensure_list(fields)

    seen = set()
    ordered: list[str] = []
    for item in fields_list:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    fields_list = ordered

    need_factor = "factor" in fields_list

    base_reqs = set(fields_list)
    auto_add_paused = False
    if (not skip_paused) and ("volume" in base_reqs) and ("paused" not in base_reqs):
        base_reqs.add("paused")
        auto_add_paused = True
    if "money" in base_reqs:
        base_reqs.update({"close", "volume"})
    if skip_paused:
        base_reqs.add("paused")
    if "high_limit" in base_reqs or "low_limit" in base_reqs:
        base_reqs.update({"close", "pre_close"})

    base_fields = list(base_reqs)

    fetch_count = max(count + 5, count)
    raw_df = get_price(
        security,
        count=fetch_count,
        fields=base_fields,
        skip_paused=False,
        fq=fq,
        fill_paused=True,
        jq_state=state,
    )

    if isinstance(raw_df, _pd.Series):
        raw_df = raw_df.to_frame(name=base_fields[0])

    current_dt = state.get("current_dt")
    cur_date = None
    if current_dt:
        try:
            cur_date = _pd.Timestamp(current_dt).date()
        except Exception:
            cur_date = None

    if cur_date is not None:
        if include_current:
            raw_df = raw_df[raw_df.index <= cur_date]
        else:
            raw_df = raw_df[raw_df.index < cur_date]

    work = raw_df.tail(count)

    if "money" in fields_list and "money" not in work.columns:
        if {"close", "volume"} <= set(work.columns):
            work["money"] = work["close"] * work["volume"]
        else:
            work["money"] = _pd.NA
    if need_factor and "factor" not in work.columns:
        work["factor"] = 1.0
    if "high_limit" in fields_list or "low_limit" in fields_list:
        try:
            limit_pct = float(options.get("limit_pct", 0.1) or 0.1)
        except Exception:
            limit_pct = 0.1
        ref_pc = work["pre_close"] if "pre_close" in work.columns else work.get("close").shift(1)
        tick = float(options.get("price_tick", 0.01) or 0.01)
        if "high_limit" in fields_list:
            work["high_limit"] = ref_pc.map(
                lambda x: _round_to_price_tick(x * (1 + limit_pct), tick) if _pd.notnull(x) else x
            )
        if "low_limit" in fields_list:
            work["low_limit"] = ref_pc.map(
                lambda x: _round_to_price_tick(x * (1 - limit_pct), tick) if _pd.notnull(x) else x
            )

    if skip_paused:
        if "paused" in work.columns:
            work = work[work["paused"] == 0]
        elif "volume" in work.columns:
            work = work[work["volume"] != 0]

    keep_cols = [c for c in fields_list if c in work.columns]
    if auto_add_paused and "paused" in work.columns and "paused" not in keep_cols:
        keep_cols.append("paused")
    work = work[keep_cols] if keep_cols else work.iloc[:, :0]
    work = work.sort_index()
    work.index.name = None

    class _JQSeries(_pd.Series):
        @property
        def _constructor(self):
            return _JQSeries

        def __getitem__(self, key):
            if isinstance(key, int):
                return self.iloc[key]
            if isinstance(key, slice):
                ok = lambda x: (x is None) or isinstance(x, int)
                if ok(key.start) and ok(key.stop) and (key.step is None or isinstance(key.step, int)):
                    return _JQSeries(self.iloc[key])
            return super().__getitem__(key)

    class _JQDataFrame(_pd.DataFrame):
        @property
        def _constructor(self):
            return _JQDataFrame

        @property
        def _constructor_sliced(self):
            return _JQSeries

        def __getitem__(self, key):
            if isinstance(key, int):
                return self.iloc[key]
            if isinstance(key, slice):
                ok = lambda x: (x is None) or isinstance(x, int)
                if ok(key.start) and ok(key.stop) and (key.step is None or isinstance(key.step, int)):
                    return _JQDataFrame(self.iloc[key])
            return super().__getitem__(key)

    if df:
        return _JQDataFrame(work)

    return {col: work[col].to_numpy(dtype=float) for col in keep_cols}

def history(
    count: int,
    unit: str = "1d",
    field: str = "avg",
    security_list=None,
    df: bool = True,
    skip_paused: bool = False,
    fq: str = "pre",
    *,
    jq_state: Optional[Dict[str, Any]] = None,
):
    """近似聚宽 history（仅支持日级）。"""

    state = _resolve_state(jq_state, "history")

    if unit.lower() not in ("1d", "d", "day"):
        raise ValueError("history 目前仅支持日级 unit=1d")
    if count <= 0:
        return _pd.DataFrame() if df else {}

    if security_list is None:
        universe = state.get("universe") or []
        if universe:
            secs = list(universe)
        else:
            g_obj = state.get("g")
            primary = getattr(g_obj, "security", None) if g_obj else None
            secs = [primary] if primary else []
    else:
        secs = _ensure_list(security_list)

    secs = [s for s in secs if s]
    if not secs:
        return _pd.DataFrame() if df else {}

    results: Dict[str, _pd.Series] = {}

    for sec in secs:
        try:
            if field in ("avg", "price"):
                base_fields = ["close", "volume"]
            elif field == "money":
                base_fields = ["close", "volume"]
            elif field == "pre_close":
                base_fields = ["close"]
            elif field == "paused":
                base_fields = ["paused"]
            else:
                base_fields = [field]

            df_single = get_price(
                sec,
                count=count,
                fields=base_fields,
                skip_paused=skip_paused,
                fq=fq,
                fill_paused=True,
                jq_state=state,
            )

            if isinstance(df_single, _pd.Series):
                df_single = df_single.to_frame(name=base_fields[0])

            if field in ("avg", "price"):
                series_field = df_single.get("close", _pd.Series([], dtype=float))
            elif field == "money":
                if {"close", "volume"} <= set(df_single.columns):
                    series_field = df_single["close"] * df_single["volume"]
                else:
                    series_field = _pd.Series([], dtype=float)
            elif field == "pre_close":
                if "close" in df_single.columns:
                    series_field = df_single["close"].shift(1)
                else:
                    series_field = _pd.Series([], dtype=float)
            elif field == "paused":
                if "paused" in df_single.columns:
                    series_field = df_single["paused"]
                else:
                    tmp = get_price(
                        sec,
                        count=count,
                        fields=["paused"],
                        skip_paused=False,
                        fq=fq,
                        fill_paused=True,
                        jq_state=state,
                    )
                    if isinstance(tmp, _pd.Series):
                        series_field = tmp
                    else:
                        series_field = tmp.get("paused", _pd.Series([], dtype=int))
            else:
                if field in df_single.columns:
                    series_field = df_single[field]
                else:
                    tmp = get_price(
                        sec,
                        count=count,
                        fields=[field],
                        skip_paused=skip_paused,
                        fq=fq,
                        fill_paused=True,
                        jq_state=state,
                    )
                    if isinstance(tmp, _pd.Series):
                        series_field = tmp
                    else:
                        series_field = tmp.get(field, _pd.Series([], dtype=float))

            series_field = series_field.tail(count)
            series_field.name = sec
            results[sec] = series_field
        except Exception:
            results[sec] = _pd.Series([], name=sec, dtype=float)

    all_index = sorted({idx for series in results.values() for idx in series.index})

    def _reindex(series: _pd.Series) -> _pd.Series:
        return series.reindex(all_index)

    if df:
        data_map = {sec: _reindex(series) for sec, series in results.items()}
        out_df = _pd.DataFrame(data_map, index=all_index)

        class _HSeries(_pd.Series):
            @property
            def _constructor(self):
                return _HSeries

            def __getitem__(self, key):
                if isinstance(key, int):
                    return self.iloc[key]
                if isinstance(key, slice):
                    ok = lambda x: (x is None) or isinstance(x, int)
                    if ok(key.start) and ok(key.stop) and (key.step is None or isinstance(key.step, int)):
                        return _HSeries(self.iloc[key])
                return super().__getitem__(key)

        class _HDataFrame(_pd.DataFrame):
            @property
            def _constructor(self):
                return _HDataFrame

            def __getitem__(self, key):
                obj = super().__getitem__(key)
                if isinstance(obj, _pd.Series):
                    return _HSeries(obj)
                return obj

        return _HDataFrame(out_df)

    return {sec: _reindex(series).to_numpy(dtype=float) for sec, series in results.items()}


def get_current_data(*, jq_state: Optional[Dict[str, Any]] = None) -> _CurrentDataProxy:
    """获取当前数据快照 - 获取所有证券的实时行情数据
    
    Returns:
        CurrentDataProxy: 数据代理对象，支持 current_data[security] 访问
    
    Example:
        current_data = get_current_data()
        price = current_data['000001.XSHE'].last_price
    """

    state = _resolve_state(jq_state, "get_current_data")
    cache = state.setdefault("_current_data_cache", {})
    marker = state.get("current_dt")

    if cache.get("__marker__") != marker:
        cache["__marker__"] = marker
        cache["__snapshots__"] = {}
    elif "__snapshots__" not in cache or not isinstance(cache["__snapshots__"], dict):
        cache["__snapshots__"] = {}

    return _CurrentDataProxy(state, cache)

# ═══════════════════════════════════════════════════════════
# 交易下单 API
# ═══════════════════════════════════════════════════════════


def order_value(
    security: str,
    value: float,
    *,
    jq_state: Optional[Dict[str, Any]] = None,
    bt_strategy: Optional[Any] = None,
):
    """按金额下单 - 最常用的下单方式"""

    state = _resolve_state(jq_state, "order_value")
    if state.get("in_warmup"):
        return None

    try:
        strategy = _resolve_strategy(state, bt_strategy, "order_value")
        data = _primary_data(strategy)
        price_ctx = _price_context(state, data)
        base_price = price_ctx["base_price"]
        exec_buy_price = price_ctx["exec_buy_price"]
        exec_sell_price = price_ctx["exec_sell_price"]
        slip_perc = price_ctx["slippage_perc"]

        total_position, closeable_position = _position_snapshot(state, strategy, security)

        options = state.setdefault("options", {})
        strict = bool(options.get("jq_order_mode_strict", False))
        enable_limit = bool(options.get("enable_limit_check", False))
        up_lim_fac = float(options.get("limit_up_factor", 1.10) or 1.10)
        down_lim_fac = float(options.get("limit_down_factor", 0.90) or 0.90)
        debug_trading = bool(options.get("debug_trading", False))

        sizing_use_raw = True
        opt_sz_raw = options.get("sizing_use_raw_open_price")
        if isinstance(opt_sz_raw, bool):
            sizing_use_raw = opt_sz_raw

        if debug_trading:
            state.setdefault("log", []).append(
                f"[sizing_slip_mode] sizing_use_raw_open_price={sizing_use_raw} slip_perc={slip_perc}"
            )

        data_close = getattr(data, "close")
        try:
            prev_close = _safe_float(data_close[-1])
        except Exception:
            prev_close = None

        tick = float(options.get("price_tick", 0.01) or 0.01)

        def _block_order(side: str, eff_price: float, status: str) -> None:
            record = OrderRecord(
                datetime=(state.get("current_dt", "").split(" ")[0]),
                symbol=state.get("primary_symbol") or str(security).split(".")[0],
                side=side,
                size=0,
                price=eff_price,
                value=0.0,
                commission=0.0,
                status=status,
            )
            state.setdefault("blocked_orders", []).append(record)

        if enable_limit and prev_close and prev_close > 0:
            up_lim = _round_to_tick(prev_close * up_lim_fac, tick)
            down_lim = _round_to_tick(prev_close * down_lim_fac, tick)
            effective_buy = exec_buy_price
            effective_sell = exec_sell_price
            if value >= 0 and effective_buy >= up_lim - 1e-9:
                _log_info(
                    state,
                    f"[limit_check] BLOCK side=BUY price={effective_buy:.4f} up_lim={up_lim:.4f} prev_close={prev_close:.4f}",
                )
                _block_order("BUY", effective_buy, "BlockedLimitUp")
                return None
            if value < 0 and effective_sell <= down_lim + 1e-9:
                _log_info(
                    state,
                    f"[limit_check] BLOCK side=SELL price={effective_sell:.4f} down_lim={down_lim:.4f} prev_close={prev_close:.4f}",
                )
                _block_order("SELL", effective_sell, "BlockedLimitDown")
                return None

        broker = getattr(strategy, "broker")
        available_cash = broker.getcash()
        lot = int(options.get("lot", 100) or 100)

        commission_rate = float(options.get("commission", 0.0003))
        min_commission = float(options.get("min_commission", 5.0))
        stamp_duty = float(options.get("stamp_duty", 0.001)) if "stamp_duty" in options else 0.001

        # 买入方向
        if value > 0:
            sizing_price = base_price if sizing_use_raw else exec_buy_price
            conservative_price = sizing_price

            conservative_flag = False
            opt_cons = options.get("order_value_conservative_prev_close")
            if isinstance(opt_cons, bool):
                conservative_flag = opt_cons

            try:
                prev_close_for_size = _safe_float(data_close[-1])
            except Exception:
                prev_close_for_size = None

            if conservative_flag and prev_close_for_size and prev_close_for_size > conservative_price:
                conservative_price = prev_close_for_size

            raw_shares = int(value // (conservative_price if conservative_flag else sizing_price))
            shares = (raw_shares // lot) * lot

            if shares <= 0:
                if debug_trading:
                    _log_info(
                        state,
                        f"[sizing] BUY abort raw_shares={raw_shares} lot={lot} est={sizing_price} conservative={conservative_price} cash={available_cash}",
                    )
                return None

            exec_price_for_cost = exec_buy_price
            gross_price_for_fee = exec_price_for_cost if (conservative_flag or sizing_use_raw) else exec_buy_price
            gross = shares * gross_price_for_fee
            comm = max(gross * commission_rate, min_commission)
            total_cost = gross + comm

            if total_cost > available_cash:
                while shares > 0:
                    gross_candidate = shares * gross_price_for_fee
                    max_cost = gross_candidate + max(gross_candidate * commission_rate, min_commission)
                    if max_cost <= available_cash:
                        break
                    shares -= lot
                if shares <= 0:
                    if debug_trading:
                        _log_info(
                            state,
                            f"[sizing] BUY zero_after_cash cons_price={gross_price_for_fee} cash={available_cash}",
                        )
                    return None

            if debug_trading:
                _log_info(
                    state,
                    f"[sizing] BUY shares={shares} sizing_price={sizing_price} exec_price={exec_buy_price} prev_close={prev_close_for_size} cons_flag={conservative_flag} cons_price={conservative_price} gross_price_used={gross_price_for_fee} gross={gross:.2f} comm_est={comm:.2f} total={total_cost:.2f} cash={available_cash:.2f}",
                )
            else:
                state.setdefault("log", []).append(
                    f"[sizing_mode] conservative_prev_close={conservative_flag} sizing_use_raw={sizing_use_raw} raw_shares={raw_shares} final_shares={shares} base_price={base_price} prev_close={prev_close_for_size} exec_price={exec_buy_price}"
                )

            if shares > 0:
                return strategy.buy(size=shares)
            return None

        if value < 0:
            value_abs = abs(value)
            max_sell_shares = closeable_position if closeable_position > 0 else 0
            if max_sell_shares <= 0:
                return None

            sizing_price = base_price if sizing_use_raw else exec_sell_price
            raw_need = int(value_abs // sizing_price) if sizing_price > 0 else 0
            tentative = (raw_need // lot) * lot if raw_need > 0 else 0
            shares = min(max_sell_shares, tentative if tentative > 0 else max_sell_shares)

            if shares <= 0:
                if value_abs >= sizing_price * lot and strict:
                    return None
                shares = max_sell_shares

            if shares <= 0:
                if debug_trading:
                    _log_info(
                        state,
                        f"[sizing] SELL abort raw_need={raw_need} lot={lot} pos={total_position} est={sizing_price}",
                    )
                return None

            if shares < max_sell_shares:
                _log_info(
                    state,
                    f"[T+1_adjust] SELL clamp shares={shares} closeable={max_sell_shares} requested={raw_need} lot={lot}",
                )

            if debug_trading:
                _log_info(
                    state,
                    f"[sizing] SELL shares={shares} sizing_price={sizing_price} exec_price={exec_sell_price} pos={total_position}",
                )

            return strategy.sell(size=shares)

    except Exception as exc:
        _log_info(state, f"[order_value_error] {type(exc).__name__}:{exc}")
    return None

def order_target(
    security: str,
    target: float,
    *,
    jq_state: Optional[Dict[str, Any]] = None,
    bt_strategy: Optional[Any] = None,
):
    """调仓到目标金额 - 智能调仓"""

    state = _resolve_state(jq_state, "order_target")
    if state.get("in_warmup"):
        return None

    try:
        strategy = _resolve_strategy(state, bt_strategy, "order_target")
        data = _primary_data(strategy)
        price_ctx = _price_context(state, data)
        base_price = price_ctx["base_price"]
        exec_buy_price = price_ctx["exec_buy_price"]
        exec_sell_price = price_ctx["exec_sell_price"]

        total_position, closeable_position = _position_snapshot(state, strategy, security)

        options = state.setdefault("options", {})
        enable_limit = bool(options.get("enable_limit_check", False))
        up_lim_fac = float(options.get("limit_up_factor", 1.10) or 1.10)
        down_lim_fac = float(options.get("limit_down_factor", 0.90) or 0.90)

        data_close = getattr(data, "close")
        try:
            prev_close = float(data_close[-1])
        except Exception:
            prev_close = None

        tick = float(options.get("price_tick", 0.01) or 0.01)

        def _block(side: str, eff_price: float, status: str) -> None:
            record = OrderRecord(
                datetime=(state.get("current_dt", "").split(" ")[0]),
                symbol=state.get("primary_symbol") or str(security).split(".")[0],
                side=side,
                size=0,
                price=eff_price,
                value=0.0,
                commission=0.0,
                status=status,
            )
            state.setdefault("blocked_orders", []).append(record)

        if enable_limit and prev_close and prev_close > 0:
            up_lim = _round_to_tick(prev_close * up_lim_fac, tick)
            down_lim = _round_to_tick(prev_close * down_lim_fac, tick)
        else:
            up_lim = down_lim = None

        lot = int(options.get("lot", 100) or 100)
        tgt_raw = int(target or 0)
        tgt = (abs(tgt_raw) // lot) * lot
        tgt = tgt if tgt_raw >= 0 else -tgt
        delta = tgt - total_position

        if delta == 0:
            return None

        if enable_limit and prev_close and prev_close > 0:
            if delta > 0 and up_lim is not None and exec_buy_price >= up_lim - 1e-9:
                _log_info(
                    state,
                    f"[limit_check] BLOCK side=BUY price={exec_buy_price:.4f} up_lim={up_lim:.4f} prev_close={prev_close:.4f}",
                )
                _block("BUY", exec_buy_price, "BlockedLimitUp")
                return None
            if delta < 0 and down_lim is not None and exec_sell_price <= down_lim + 1e-9:
                _log_info(
                    state,
                    f"[limit_check] BLOCK side=SELL price={exec_sell_price:.4f} down_lim={down_lim:.4f} prev_close={prev_close:.4f}",
                )
                _block("SELL", exec_sell_price, "BlockedLimitDown")
                return None

        if delta > 0:
            return strategy.buy(size=delta)

        sell_needed = abs(delta)
        max_sell = closeable_position if closeable_position > 0 else 0
        if max_sell <= 0:
            return None

        sell_size = min(max_sell, sell_needed)
        if sell_size % lot != 0 and sell_size != max_sell:
            sell_size = (sell_size // lot) * lot
            if sell_size <= 0 and max_sell > 0:
                sell_size = max_sell

        if sell_size <= 0:
            return None

        if sell_size < sell_needed:
            _log_info(
                state,
                f"[T+1_adjust] SELL clamp target_delta={sell_needed} closeable={max_sell} final={sell_size}",
            )

        return strategy.sell(size=sell_size)

    except Exception as exc:
        _log_info(state, f"[order_target_error] {type(exc).__name__}:{exc}")
    return None

def order(
    security: str,
    amount: int,
    *,
    jq_state: Optional[Dict[str, Any]] = None,
    bt_strategy: Optional[Any] = None,
):
    """按股数下单 - 基础下单接口"""

    state = _resolve_state(jq_state, "order")
    if state.get("in_warmup"):
        return None

    try:
        strategy = _resolve_strategy(state, bt_strategy, "order")
        data = _primary_data(strategy)
        price_ctx = _price_context(state, data)
        base_price = price_ctx["base_price"]

        if amount > 0:
            return order_value(
                security,
                amount * base_price,
                jq_state=state,
                bt_strategy=strategy,
            )
        if amount < 0:
            return order_value(
                security,
                amount * base_price,
                jq_state=state,
                bt_strategy=strategy,
            )
        return None

    except Exception as exc:
        _log_info(state, f"[order_error] {type(exc).__name__}:{exc}")
    return None


def order_target_value(
    security: str,
    value: float,
    *,
    jq_state: Optional[Dict[str, Any]] = None,
    bt_strategy: Optional[Any] = None,
):
    """根据目标市值调仓。"""

    state = _resolve_state(jq_state, "order_target_value")
    if state.get("in_warmup"):
        return None

    try:
        strategy = _resolve_strategy(state, bt_strategy, "order_target_value")
        data = _primary_data(strategy)
        price_ctx = _price_context(state, data)
        base_price = price_ctx["base_price"]

        options = state.setdefault("options", {})
        lot = int(options.get("lot", 100) or 100)

        target_value = float(value or 0.0)
        if target_value < 0:
            target_value = 0.0

        sizing_use_raw = True
        opt_sz_raw = options.get("sizing_use_raw_open_price")
        if isinstance(opt_sz_raw, bool):
            sizing_use_raw = opt_sz_raw

        price_for_size = base_price if sizing_use_raw else max(price_ctx["exec_buy_price"], base_price)
        if price_for_size <= 0:
            return None

        raw_target = int(target_value // price_for_size)
        if raw_target < 0:
            raw_target = 0
        target_shares = (raw_target // lot) * lot

        return order_target(
            security,
            target_shares,
            jq_state=state,
            bt_strategy=strategy,
        )

    except Exception as exc:
        _log_info(state, f"[order_target_value_error] {type(exc).__name__}:{exc}")
    return None


def order_target_percent(
    security: str,
    percent: float,
    *,
    jq_state: Optional[Dict[str, Any]] = None,
    bt_strategy: Optional[Any] = None,
):
    """根据组合市值占比调仓。"""

    state = _resolve_state(jq_state, "order_target_percent")
    if state.get("in_warmup"):
        return None

    try:
        strategy = _resolve_strategy(state, bt_strategy, "order_target_percent")
        broker = getattr(strategy, "broker")
        total_value = float(broker.getvalue()) if broker else 0.0
        if total_value <= 0:
            return None

        target_percent = float(percent or 0.0)
        target_value = total_value * target_percent

        return order_target_value(
            security,
            target_value,
            jq_state=state,
            bt_strategy=strategy,
        )

    except Exception as exc:
        _log_info(state, f"[order_target_percent_error] {type(exc).__name__}:{exc}")
    return None


# ═══════════════════════════════════════════════════════════
# 策略配置 API
# ═══════════════════════════════════════════════════════════


def _log_scheduler(state: Dict[str, Any], kind: str, func: Any, time: str) -> None:
    """Internal: Log scheduler registration."""
    try:
        name = getattr(func, "__name__", str(func))
        state.setdefault("log", []).append(f"[Scheduler] register {kind} {name} at {time}")
    except Exception:
        pass


def _log_info(state: Dict[str, Any], message: str) -> None:
    """Internal: Log information message."""
    logger = state.get("logger")
    if logger is not None:
        try:
            logger.info(message)
            return
        except Exception:
            pass
    state.setdefault("log", []).append(str(message))


def set_benchmark(code: str, *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """设置基准 - 用于收益对比"""

    state = _ensure_state(jq_state, "set_benchmark")
    state["benchmark"] = _normalize_code(code)

def set_option(name: str, value: Any, *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """设置选项 - 配置回测参数"""

    state = _ensure_state(jq_state, "set_option")
    state.setdefault("options", {})[name] = value
    state.setdefault("log", []).append(f"[set_option] {name}={value}")

def set_commission(obj=None, *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """设置佣金与成本参数。"""

    state = _ensure_state(jq_state, "set_commission")
    if obj is None:
        return

    options = state.setdefault("options", {})
    log = state.setdefault("log", [])

    def _decode(keys):
        if isinstance(obj, dict):
            for key in keys:
                if key in obj:
                    return obj[key]
        for key in keys:
            if hasattr(obj, key):
                return getattr(obj, key)
        return None

    if isinstance(obj, (int, float)):
        options["commission"] = float(obj)
        log.append(f"[set_commission] commission={float(obj)}")
        return

    mapping = {
        "commission": ["commission", "buy_cost", "open_commission", "close_commission"],
        "min_commission": ["min_commission", "min_commission_cost", "min_trade_cost"],
        "tax": ["tax", "stamp_duty"],
        "open_tax": ["open_tax"],
        "close_tax": ["close_tax"],
    }

    updated = []
    for target, keys in mapping.items():
        value = _decode(keys)
        if value is None:
            continue
        try:
            options[target] = float(value)
            updated.append(f"{target}={float(value)}")
        except Exception:
            continue

    if not updated:
        log.append("[set_commission_warning] no_fields_recognized")
    else:
        log.append(f"[set_commission] {';'.join(updated)}")

def set_slippage(obj=None, type=None, ref=None, *, jq_state: Optional[Dict[str, Any]] = None) -> None:  # noqa: A002
    """设置滑点 - 模拟真实交易成本"""

    state = _ensure_state(jq_state, "set_slippage")
    if obj is None:
        return

    text = str(obj)
    log = state.setdefault("log", [])
    try:
        m_price = re.search(r"PriceRelatedSlippage\s*\(\s*([0-9eE\.+-]+)\s*\)", text)
        m_fixed = re.search(r"FixedSlippage\s*\(\s*([0-9eE\.+-]+)\s*\)", text)
        if m_price:
            val = float(m_price.group(1))
            state.setdefault("options", {})["slippage_perc"] = val
            log.append(f"[set_slippage] PriceRelatedSlippage perc={val}")
            return
        if m_fixed:
            val = float(m_fixed.group(1))
            state.setdefault("options", {})["fixed_slippage"] = val
            log.append(f"[set_slippage] FixedSlippage value={val}")
            return
        val = float(obj)
        state.setdefault("options", {})["slippage_perc"] = val
        log.append(f"[set_slippage] perc={val}")
    except Exception:
        log.append(f"[set_slippage_warning] unrecognized={text}")

# 📅 调度器API
def run_daily(func, time="09:30", *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """每日定时执行 - 最常用的调度方式"""
    state = _resolve_state(jq_state, "run_daily")
    from backend.modules.s_3_backtest_engine.scheduler.task_queue import register_task

    register_task(state, "daily", time, func)
    _log_scheduler(state, "daily", func, time)

def run_weekly(func, time="09:30", *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """每周定时执行"""
    state = _resolve_state(jq_state, "run_weekly")
    from backend.modules.s_3_backtest_engine.scheduler.task_queue import register_task

    register_task(state, "weekly", time, func)
    _log_scheduler(state, "weekly", func, time)

def run_monthly(func, time="09:30", *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """每月定时执行"""
    state = _resolve_state(jq_state, "run_monthly")
    from backend.modules.s_3_backtest_engine.scheduler.task_queue import register_task

    register_task(state, "monthly", time, func)
    _log_scheduler(state, "monthly", func, time)


# ═══════════════════════════════════════════════════════════
# 生命周期 API
# ═══════════════════════════════════════════════════════════


def before_trading_start(func, *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """开盘前执行 - 数据准备阶段"""
    state = _resolve_state(jq_state, "before_trading_start")
    from backend.modules.s_3_backtest_engine.scheduler.lifecycle import register_lifecycle_task

    register_lifecycle_task(state, "before_trading_start", func)

def after_trading_end(func, *, jq_state: Optional[Dict[str, Any]] = None) -> None:
    """收盘后执行 - 结算阶段"""
    state = _resolve_state(jq_state, "after_trading_end")
    from backend.modules.s_3_backtest_engine.scheduler.lifecycle import register_lifecycle_task

    register_lifecycle_task(state, "after_trading_end", func)


# ═══════════════════════════════════════════════════════════
# 记录与日志 API
# ═══════════════════════════════════════════════════════════


def record(*, jq_state: Optional[Dict[str, Any]] = None, **kwargs: Any) -> None:
    """记录自定义数据 - 用于分析和调试"""

    state = _ensure_state(jq_state, "record")
    if state.get("in_warmup"):
        return

    payload = dict(kwargs)
    if "dt" not in payload:
        marker = state.get("current_dt") or state.get("latest_dt") or state.get("user_start")
        if isinstance(marker, str) and marker.strip():
            payload["dt"] = marker.strip()
        else:
            payload["dt"] = None

    records = state.setdefault("records", [])
    records.append(payload)

    marker = payload.get("dt")
    if isinstance(marker, str) and marker.strip():
        state["latest_dt"] = marker.strip()


def log_scheduler(state: Dict[str, Any], kind: str, func: Any, time: str) -> None:
    """记录调度器注册信息 - 用户可调用的日志API"""
    _log_scheduler(state, kind, func, time)


def log_info(state: Dict[str, Any], message: str) -> None:
    """记录日志信息 - 用户可调用的日志API"""
    _log_info(state, message)


