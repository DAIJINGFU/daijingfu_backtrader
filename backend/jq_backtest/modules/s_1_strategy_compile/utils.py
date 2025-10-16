"""策略编译模块的通用工具函数库"""
from __future__ import annotations

import inspect
import math
import re
from collections.abc import Iterable
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd

__all__ = [
    "parse_date",
    "round_to_price_tick",
    "normalize_code",
    "ensure_list",
    "safe_float",
    "merge_position",
    # 内部辅助函数（从 jq_api.py 迁移）
    "ensure_state",
    "resolve_state",
    "resolve_strategy",
    "primary_data",
    "position_snapshot",
    "price_context",
    "normalize_security_key",
    "is_null",
    "to_float",
    "to_int",
    "first_valid_value",
    "extract_datetime_series",
    "resolve_dataframe_for_security",
    "build_snapshot_for_security",
    "load_trading_calendar",
]

def parse_date(value: Any) -> Optional[date]:
    """将用户输入转换为 date 实例（如果可能）"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("/", "-")).date()
    except (TypeError, ValueError):
        return None

def round_to_price_tick(value: Any, tick: float) -> Any:
    """将价格向下舍入到最近的价格档位"""
    try:
        price = float(value)
        step = float(tick)
        if step <= 0:
            return price
        return math.floor(price / step + 1e-9) * step
    except (TypeError, ValueError):
        return value


_CODE_SUFFIX_MAP = {
    "SH": "XSHG",
    "SZ": "XSHE",
    "SHSE": "XSHG",
    "SZSE": "XSHE",
}


def normalize_code(code: Any) -> str:
    """将证券代码标准化为聚宽风格的 XXXXX.XSHE/XSHG 格式"""

    if code is None:
        return ""

    text = str(code).strip()
    if not text:
        return ""

    upper = text.upper().replace(" ", "")

    # 如果用点号或破折号分隔，则分割前缀和主体
    if "." in upper:
        body, suffix = upper.split(".", 1)
        mapped_suffix = _CODE_SUFFIX_MAP.get(suffix, suffix)
        return f"{body}{'.' if mapped_suffix else ''}{mapped_suffix}"

    if "-" in upper:
        body, suffix = upper.split("-", 1)
        mapped_suffix = _CODE_SUFFIX_MAP.get(suffix, suffix)
        return f"{body}{'.' if mapped_suffix else ''}{mapped_suffix}"

    match = re.fullmatch(r"(SH|SZ)(\d{6})", upper)
    if match:
        prefix, digits = match.groups()
        mapped_suffix = _CODE_SUFFIX_MAP[prefix]
        return f"{digits}.{mapped_suffix}"

    digits_match = re.fullmatch(r"\d{6}", upper)
    if digits_match:
        digits = digits_match.group(0)
        mapped_suffix = "XSHG" if digits.startswith(("5", "6")) else "XSHE"
        return f"{digits}.{mapped_suffix}"

    return upper


def ensure_list(value: Any) -> list[Any]:
    """将值转换为列表，同时保持标量完整"""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, dict):
        return list(value.keys())
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return [value]


def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """将值转换为浮点数，同时处理空值、NaN 和错误"""

    if value is None:
        return default
    try:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return default
            parsed = float(stripped)
        else:
            parsed = float(value)
    except (TypeError, ValueError):
        return default

    if math.isnan(parsed) or math.isinf(parsed):
        return default
    return parsed


def merge_position(
    strategy: Any,
    jq_state: Optional[Dict[str, Any]] = None,
    *,
    fallback_symbol: str = "data0",
) -> Dict[str, Dict[str, int]]:
    """从 Backtrader 策略实例构建聚宽风格的持仓快照"""

    if strategy is None or not hasattr(strategy, "position"):
        return {}

    try:
        bt_position = getattr(strategy, "position")
    except Exception:
        return {}

    try:
        total_amount = int(getattr(bt_position, "size", 0) or 0)
    except Exception:
        total_amount = 0

    if total_amount == 0:
        return {}

    security = fallback_symbol
    bought_today = 0

    if isinstance(jq_state, dict):
        g_obj = jq_state.get("g")
        security = getattr(g_obj, "security", security) if g_obj else security

        current_dt_raw = jq_state.get("current_dt", "")
        day_token = str(current_dt_raw).split(" ")[0] if current_dt_raw else ""
        try:
            day_map = jq_state.get("_daily_bought", {}) or {}
            bought_today = int(day_map.get(day_token, 0) or 0)
        except Exception:
            bought_today = 0

    closeable = max(0, total_amount - bought_today)

    return {
        str(security) if security is not None else fallback_symbol: {
            "closeable_amount": closeable,
            "total_amount": total_amount,
        }
    }


# ═══════════════════════════════════════════════════════════
# 内部辅助函数（从 jq_api.py 迁移）
# ═══════════════════════════════════════════════════════════
# 以下函数是聚宽 API 实现使用的内部工具。
# 它们不是公开 API 的一部分。
# ═══════════════════════════════════════════════════════════


def ensure_state(jq_state: Optional[Dict[str, Any]], func_name: str) -> Dict[str, Any]:
    """确保提供了 jq_state，如果没有则抛出 RuntimeError"""
    if jq_state is None:
        raise RuntimeError(f"{func_name} requires jq_state context")
    return jq_state


def resolve_state(jq_state: Optional[Dict[str, Any]], func_name: str) -> Dict[str, Any]:
    """从提供的参数或调用者的上下文中解析 jq_state"""
    if jq_state is not None:
        return jq_state
    frame = inspect.currentframe()
    current = frame.f_back if frame else None
    try:
        while current:
            candidate = current.f_locals.get("jq_state") or current.f_globals.get("jq_state")
            if candidate is not None:
                return candidate
            current = current.f_back
    finally:
        del frame
    raise RuntimeError(f"{func_name} requires jq_state context")


def resolve_strategy(state: Dict[str, Any], bt_strategy: Optional[Any], func_name: str):
    """从状态或参数中解析 Backtrader 策略实例"""
    if bt_strategy is not None:
        return bt_strategy
    candidate = state.get("_strategy_instance")
    if candidate is not None:
        return candidate
    raise RuntimeError(f"{func_name} requires a Backtrader strategy context")


def primary_data(strategy: Any):
    """从 Backtrader 策略中获取主数据源"""
    data = getattr(strategy, "data", None)
    if data is None:
        data = getattr(strategy, "data0", None)
    if data is None:
        datas = getattr(strategy, "datas", None)
        if datas:
            data = datas[0]
    if data is None:
        raise RuntimeError("strategy has no data feed attached")
    return data


def position_snapshot(
    state: Dict[str, Any],
    strategy: Any,
    security: Any,
) -> tuple[int, int]:
    """返回请求证券的总持仓量和可平仓量"""

    fallback = security or state.get("primary_symbol") or None
    if fallback is None:
        g_obj = state.get("g")
        fallback = getattr(g_obj, "security", None) if g_obj else None
    snapshot = merge_position(strategy, jq_state=state, fallback_symbol=str(fallback or "data0"))
    if not snapshot:
        return 0, 0

    candidates: list[str] = []
    if security is not None:
        sec_text = str(security)
        if sec_text:
            candidates.append(sec_text)
            try:
                normalized = normalize_code(sec_text)
                if normalized not in candidates:
                    candidates.append(normalized)
            except Exception:
                pass
            try:
                base = normalize_security_key(sec_text)
                if base and base not in candidates:
                    candidates.append(base)
            except Exception:
                pass

    primary_symbol = state.get("primary_symbol")
    if primary_symbol:
        primary_text = str(primary_symbol)
        if primary_text not in candidates:
            candidates.append(primary_text)

    g_obj = state.get("g")
    g_security = getattr(g_obj, "security", None) if g_obj else None
    if g_security:
        g_text = str(g_security)
        if g_text not in candidates:
            candidates.append(g_text)

    info = None
    for key in candidates:
        if key in snapshot:
            info = snapshot[key]
            break

    if info is None:
        info = next(iter(snapshot.values()))

    total = int(info.get("total_amount", 0) or 0)
    closeable = int(info.get("closeable_amount", total) or 0)
    if closeable > total:
        closeable = total
    if closeable < 0:
        closeable = 0
    return total, closeable


def price_context(state: Dict[str, Any], data: Any) -> Dict[str, Any]:
    """计算包含滑点的订单执行价格上下文"""
    options = state.get("options", {})
    fill_price = str(options.get("fill_price", "open")).lower()
    if fill_price == "close":
        base = float(getattr(data, "close")[0])
    else:
        if hasattr(data, "open"):
            base = float(getattr(data, "open")[0])
        else:
            base = float(getattr(data, "close")[0])
    if base <= 0:
        raise ValueError("base price must be positive")

    slip_perc = float(options.get("slippage_perc", 0.0) or 0.0)
    half = slip_perc / 2.0

    def _round_buy(price: float) -> float:
        return math.floor(price * 100) / 100.0

    def _round_sell(price: float) -> float:
        return math.ceil(price * 100) / 100.0

    exec_buy = _round_buy(base * (1 + half)) if slip_perc else base
    exec_sell = _round_sell(base * (1 - half)) if slip_perc else base

    return {
        "base_price": base,
        "exec_buy_price": exec_buy,
        "exec_sell_price": exec_sell,
        "slippage_perc": slip_perc,
        "fill_price": fill_price,
    }


def normalize_security_key(value: Any) -> Optional[str]:
    """将证券标识符标准化为基本键（不含交易所后缀）"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        normalized = normalize_code(text)
    except Exception:
        normalized = text
    base = normalized.split(".")[0] if "." in normalized else normalized
    base = base.strip()
    return base or None


def is_null(value: Any) -> bool:
    """检查值是否为空（None 或 NaN）"""
    try:
        return bool(pd.isna(value))
    except Exception:
        return value is None


def to_float(value: Any) -> Optional[float]:
    """将值转换为浮点数，如果转换失败或值为空则返回 None"""
    if is_null(value):
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_int(value: Any) -> Optional[int]:
    """将值转换为整数，如果转换失败或值为空则返回 None"""
    if is_null(value):
        return None
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return None


def first_valid_value(row: Any, candidates: tuple[str, ...]) -> Optional[float]:
    """从给定候选字段名的行中提取第一个有效的数值"""
    for name in candidates:
        if isinstance(row, dict):
            value = row.get(name)
        else:
            value = row[name] if name in row else None
        result = to_float(value)
        if result is not None:
            return result
    return None


def extract_datetime_series(df: pd.DataFrame) -> Optional[pd.Series]:
    """从 DataFrame 的列或索引中提取日期时间序列"""
    for candidate in ("datetime", "trade_time", "time", "date"):
        if candidate in df.columns:
            series = pd.to_datetime(df[candidate], errors="coerce")
            if series.notna().any():
                return series
    index = df.index
    if isinstance(index, pd.DatetimeIndex):
        return pd.Series(index, index=index)
    try:
        series = pd.to_datetime(index, errors="coerce")
        if series.notna().any():
            return pd.Series(series, index=df.index)
    except Exception:
        pass
    return None


def resolve_dataframe_for_security(state: Dict[str, Any], base: str) -> Optional[pd.DataFrame]:
    """从 jq_state 中解析特定证券的 DataFrame"""
    hist_map = state.get("history_df_map")
    if isinstance(hist_map, dict) and hist_map:
        if base in hist_map:
            return hist_map[base]
        for key, value in hist_map.items():
            normalized = normalize_security_key(key)
            if normalized == base:
                return value
    global_df = state.get("history_df")
    if global_df is None:
        return None
    g_obj = state.get("g")
    primary = getattr(g_obj, "security", None) if g_obj is not None else None
    if primary and normalize_security_key(primary) == base:
        return global_df
    if not hist_map:
        return global_df
    return None


def build_snapshot_for_security(state: Dict[str, Any], base: str):
    """为特定证券构建 CurrentSnapshot 对象
    
    注意：返回可用于构造 CurrentSnapshot 的字典。
    实际的 CurrentSnapshot 类在 jq_models.py 中定义。
    """
    df = resolve_dataframe_for_security(state, base)
    if df is None or len(df) == 0:
        raise KeyError(f"security {base!r} not available")

    working = df.copy()
    dt_series = extract_datetime_series(working)
    if dt_series is not None:
        mask = dt_series.notna()
        working = working.loc[mask].copy()
        working["_jq_datetime"] = dt_series.loc[mask].to_numpy()
    else:
        working["_jq_datetime"] = pd.NaT

    marker = state.get("current_dt")
    cur_ts = None
    if marker:
        try:
            cur_ts = pd.to_datetime(marker, errors="coerce")
        except Exception:
            cur_ts = None

    if cur_ts is not None and pd.notna(cur_ts):
        eligible = working[working["_jq_datetime"] <= cur_ts]
        if not eligible.empty:
            working = eligible

    if working.empty:
        working = df.copy()
        working["_jq_datetime"] = pd.NaT

    row = working.iloc[-1]
    prev = working.iloc[-2] if len(working) >= 2 else None
    row_dt = row.get("_jq_datetime") if "_jq_datetime" in row else None

    close_price = to_float(row.get("close"))
    open_price = to_float(row.get("open"))
    high_price = to_float(row.get("high"))
    low_price = to_float(row.get("low"))
    volume_val = to_float(row.get("volume"))

    last_price = first_valid_value(row, ("last_price", "price", "close", "open"))
    if last_price is None:
        last_price = close_price

    pre_close = to_float(row.get("pre_close"))
    if pre_close is None and prev is not None:
        pre_close = to_float(prev.get("close"))

    paused_val = row.get("paused") if "paused" in row else None
    paused_int = to_int(paused_val) if paused_val is not None else None
    if paused_int is None:
        paused_int = 1 if (volume_val == 0) else 0
    is_paused = bool(paused_int)

    options = state.get("options", {})
    try:
        limit_pct = float(options.get("limit_pct", 0.1) or 0.1)
    except Exception:
        limit_pct = 0.1
    try:
        price_tick = float(options.get("price_tick", 0.01) or 0.01)
    except Exception:
        price_tick = 0.01

    high_limit = to_float(row.get("high_limit"))
    if high_limit is None and pre_close is not None:
        high_limit = round_to_price_tick(pre_close * (1 + limit_pct), price_tick)

    low_limit = to_float(row.get("low_limit"))
    if low_limit is None and pre_close is not None:
        low_limit = round_to_price_tick(pre_close * (1 - limit_pct), price_tick)

    row_dt_py = None
    if row_dt is not None and not is_null(row_dt):
        try:
            row_dt_py = pd.Timestamp(row_dt).to_pydatetime()
        except Exception:
            row_dt_py = None

    payload = {
        "security": normalize_code(base),
        "last_price": last_price,
        "close": close_price,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "volume": volume_val or 0.0,
        "pre_close": pre_close,
        "high_limit": high_limit,
        "low_limit": low_limit,
        "paused": paused_int,
        "is_paused": is_paused,
        "datetime": row_dt_py,
    }

    return payload


def load_trading_calendar(data_dir: str = None) -> Optional[set[str]]:
    """
    加载交易日历数据。

    参数:
        data_dir: 数据目录路径，默认为 None（自动推断为 ../data）

    返回:
        交易日期的字符串集合（YYYY-MM-DD 格式），加载失败返回 None

    说明:
        - 默认从 ../data/trading_calendar.csv 读取交易日历
        - 自动识别日期列（优先使用 'date' 列）
        - 将日期转换为 YYYY-MM-DD 格式的字符串集合
        - 加载失败时返回 None 而不抛出异常

    示例:
        >>> dates = load_trading_calendar()
        >>> if dates:
        >>>     print(f"加载了 {len(dates)} 个交易日")
        >>>     print("2025-10-14" in dates)  # 检查某日是否为交易日
    """
    try:
        import os

        # 构建路径
        if data_dir is None:
            # 默认路径：相对于当前文件的 ../../data
            current_file = os.path.abspath(__file__)
            module_dir = os.path.dirname(current_file)  # s_1_strategy_compile
            parent_dir = os.path.dirname(module_dir)     # modules
            data_dir = os.path.join(os.path.dirname(parent_dir), "data")

        cal_path = os.path.join(data_dir, "trading_calendar.csv")
        cal_path = os.path.abspath(cal_path)

        # 检查文件存在
        if not os.path.exists(cal_path):
            return None

        # 读取 CSV
        cal_df = pd.read_csv(cal_path)
        if cal_df.empty:
            return None

        # 识别日期列
        col = "date" if "date" in cal_df.columns else cal_df.columns[0]

        # 转换为日期字符串集合
        dates = set(pd.to_datetime(cal_df[col]).dt.date.astype(str))

        return dates if dates else None

    except Exception:
        return None

