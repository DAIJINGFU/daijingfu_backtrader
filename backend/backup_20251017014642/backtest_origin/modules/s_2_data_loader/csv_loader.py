"""CSV 数据加载与 Backtrader feed 构建工具。"""
from __future__ import annotations

import os
import re
from typing import Optional, Tuple, List

import pandas as pd
import backtrader as bt

__all__ = [
    "DataNotFound",
    "normalize_symbol",
    "resolve_price_file",
    "load_price_dataframe",
    "load_bt_feed",
]


class DataNotFound(Exception):
    """表示在预期路径中未找到所需的行情数据文件。"""


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_DEFAULT_DATA_DIR = os.path.join(_PROJECT_ROOT, "data")
_DEFAULT_STOCKDATA_DIR = os.path.join(_PROJECT_ROOT, "stockdata", "stockdata")

_RENAME_MAP = {
    "日期": "datetime",
    "交易日期": "datetime",
    "开盘": "open",
    "开盘价": "open",
    "最高": "high",
    "最高价": "high",
    "最低": "low",
    "最低价": "low",
    "收盘": "close",
    "收盘价": "close",
    "成交量": "volume",
    "成交额": "amount",
    "股票代码": "code",
    "代码": "code",
}

_symbol_ex_pattern = re.compile(r"^(?P<code>\d{6})(?:\.(?P<ex>[A-Za-z]{2,4}))?$")

_exchange_map = {
    "XSHG": "SH",
    "XSHG2": "SH",
    "SH": "SH",
    "SS": "SH",
    "XSHE": "SZ",
    "SZ": "SZ",
    "SZSE": "SZ",
}

_minute_prefix = {"SH": "sh", "SZ": "sz"}


def normalize_symbol(symbol: str) -> Tuple[str, Optional[str]]:
    """规范证券代码格式，返回 (code, exchange) 形式。"""

    s = symbol.strip()
    s = s.replace(".xshg", ".XSHG").replace(".xshe", ".XSHE")
    match = _symbol_ex_pattern.match(s)
    if not match:
        core = re.sub(r"[_\.].*$", "", s)
        if len(core) == 6 and core.isdigit():
            return core, None
        return s, None
    code = match.group("code")
    exchange = match.group("ex")
    exchange = _exchange_map.get(exchange.upper()) if exchange else None
    return code, exchange


def _candidate_daily_files(code: str, adjust: str, use_real_price: bool | None = None) -> List[str]:
    seq_raw = [f"{code}_daily.csv", f"{code}_日.csv"]
    seq_qfq = [f"{code}_daily_qfq.csv", f"{code}_日_qfq.csv"]
    seq_hfq = [f"{code}_daily_hfq.csv", f"{code}_日_hfq.csv"]
    if adjust == "raw":
        return seq_raw + seq_qfq + seq_hfq
    if adjust == "qfq":
        return seq_qfq + seq_raw + seq_hfq
    if adjust == "hfq":
        return seq_hfq + seq_raw + seq_qfq
    if use_real_price:
        return seq_raw + seq_qfq + seq_hfq
    return seq_qfq + seq_raw + seq_hfq


def resolve_price_file(
    symbol: str,
    start: str,
    end: str,
    frequency: str = "daily",
    adjust: str = "auto",
    prefer_stockdata: bool = True,
    data_root: Optional[str] = None,
    stockdata_root: Optional[str] = None,
    use_real_price: bool | None = None,
) -> str:
    """根据参数选择最合适的行情文件路径。"""

    code, exchange = normalize_symbol(symbol)
    data_root = data_root or os.environ.get("BACKTEST_DATA_ROOT", _DEFAULT_DATA_DIR)
    stockdata_root = stockdata_root or os.environ.get("BACKTEST_STOCKDATA_ROOT", _DEFAULT_STOCKDATA_DIR)

    freq = frequency.lower()

    benchmark_root_env = os.environ.get("BACKTEST_BENCHMARK_ROOT")
    benchmark_dirs: List[str] = []
    if benchmark_root_env and os.path.isdir(benchmark_root_env):
        benchmark_dirs.append(benchmark_root_env)
    builtin_benchmark_dir = os.path.join(stockdata_root, "基准指数数据")
    if os.path.isdir(builtin_benchmark_dir):
        benchmark_dirs.append(builtin_benchmark_dir)
    if freq == "daily" and benchmark_dirs:
        for bench_dir in benchmark_dirs:
            for fname in (
                f"{code}_日.csv",
                f"{code}_daily.csv",
                f"{code}_daily_qfq.csv",
                f"{code}_daily_hfq.csv",
            ):
                path = os.path.join(bench_dir, fname)
                if os.path.exists(path):
                    return path

    if prefer_stockdata and os.path.isdir(stockdata_root):
        if freq == "1min":
            if not exchange:
                exchange = "SH" if code.startswith("6") else "SZ"
            prefix = _minute_prefix.get(exchange, exchange.lower())
            base_old = f"{prefix}{code}"
            base_new = f"{code}.{exchange}"

            def _minute_name_candidates(base: str) -> List[str]:
                if adjust == "raw":
                    suffixes = ["", "_qfq", "_hfq"]
                elif adjust == "qfq":
                    suffixes = ["_qfq", "", "_hfq"]
                elif adjust == "hfq":
                    suffixes = ["_hfq", "", "_qfq"]
                else:
                    suffixes = ["", "_qfq", "_hfq"] if use_real_price else ["_qfq", "", "_hfq"]
                names: List[str] = []
                for suffix in suffixes:
                    base_name = base + suffix
                    for ext in (".csv", ".cs"):
                        names.append(base_name + ext)
                return names

            minute_dir = os.path.join(stockdata_root, "1min")
            symbol_upper = symbol.upper()
            prefer_old = symbol_upper.endswith(".XSHE") or symbol_upper.endswith(".XSHG")
            name_candidates: List[str] = []
            if prefer_old:
                name_candidates.extend(_minute_name_candidates(base_old))
                name_candidates.extend(_minute_name_candidates(base_new))
            else:
                name_candidates.extend(_minute_name_candidates(base_new))
                name_candidates.extend(_minute_name_candidates(base_old))

            tried: List[str] = []
            for fname in name_candidates:
                path = os.path.join(minute_dir, fname)
                tried.append(path)
                if os.path.exists(path):
                    return path
            if os.path.isdir(minute_dir):
                for fname in os.listdir(minute_dir):
                    if fname.startswith(base_new) or fname.startswith(base_old):
                        return os.path.join(minute_dir, fname)
            raise DataNotFound(f"分钟数据缺失: code={code} ex={exchange} tried={tried}")

        if freq in ("daily", "weekly", "monthly"):
            subdir = os.path.join(stockdata_root, "1d_1w_1m", code)
            if not os.path.isdir(subdir):
                return _resolve_legacy_daily(code, adjust, data_root)
            if freq == "daily":
                for fname in _candidate_daily_files(code, adjust, use_real_price):
                    path = os.path.join(subdir, fname)
                    if os.path.exists(path):
                        return path
            else:
                base = f"{code}_{'weekly' if freq == 'weekly' else 'monthly'}"
                if adjust == "qfq":
                    candidates = [base + "_qfq.csv", base + "_hfq.csv", base + ".csv"]
                elif adjust == "hfq":
                    candidates = [base + "_hfq.csv", base + "_qfq.csv", base + ".csv"]
                elif adjust == "raw":
                    candidates = [base + ".csv", base + "_qfq.csv", base + "_hfq.csv"]
                else:
                    candidates = [base + ".csv", base + "_qfq.csv", base + "_hfq.csv"] if use_real_price else [base + "_qfq.csv", base + ".csv", base + "_hfq.csv"]
                tried_candidates = []
                for fname in candidates:
                    path = os.path.join(subdir, fname)
                    tried_candidates.append(path)
                    if os.path.exists(path):
                        return path
                for fname in os.listdir(subdir):
                    if fname.startswith(base):
                        return os.path.join(subdir, fname)
                raise DataNotFound(f"未找到{freq}文件: {subdir}; tried={tried_candidates}")
        else:
            raise ValueError(f"不支持频率: {frequency}")

    if freq != "daily":
        raise DataNotFound("旧 data 目录仅支持日线 (daily)")
    return _resolve_legacy_daily(code, adjust, data_root)


def _resolve_legacy_daily(code: str, adjust: str, data_root: str) -> str:
    for fname in _candidate_daily_files(code, adjust):
        path = os.path.join(data_root, fname)
        if os.path.exists(path):
            return path
    raw = os.path.join(data_root, f"{code}.csv")
    if os.path.exists(raw):
        return raw
    raise DataNotFound(f"未找到任何可用日线文件: {code}")


def _read_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    rename_cols = {c: _RENAME_MAP[c] for c in df.columns if c in _RENAME_MAP}
    if rename_cols:
        df = df.rename(columns=rename_cols)
    if "datetime" not in df.columns:
        for cand in ("date", "Date", "日期", "交易日期"):
            if cand in df.columns:
                df = df.rename(columns={cand: "datetime"})
                break
    if "datetime" not in df.columns:
        raise ValueError(f"文件缺少日期列: {path}")
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    try:
        if hasattr(df["datetime"].dt, "tz") and df["datetime"].dt.tz is not None:
            df["datetime"] = df["datetime"].dt.tz_convert(None)
    except Exception:
        try:
            df["datetime"] = df["datetime"].dt.tz_localize(None)
        except Exception:
            pass
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


def load_price_dataframe(
    symbol: str,
    start: str,
    end: str,
    frequency: str = "daily",
    adjust: str = "auto",
    prefer_stockdata: bool = True,
    data_root: Optional[str] = None,
    stockdata_root: Optional[str] = None,
    use_real_price: bool | None = None,
    out_path_holder: dict | None = None,
) -> pd.DataFrame:
    """按参数加载行情数据并裁剪到指定日期区间。"""

    try:
        path = resolve_price_file(
            symbol,
            start,
            end,
            frequency,
            adjust,
            prefer_stockdata,
            data_root,
            stockdata_root,
            use_real_price,
        )
        df = _read_csv(path)
        if out_path_holder is not None:
            out_path_holder["path"] = path
    except DataNotFound:
        if frequency in ("weekly", "monthly"):
            daily_df = load_price_dataframe(
                symbol,
                start,
                end,
                "daily",
                adjust,
                prefer_stockdata,
                data_root,
                stockdata_root,
            )
            if daily_df.empty:
                return daily_df
            daily_df = daily_df.set_index("datetime")
            rule = "W-FRI" if frequency == "weekly" else "M"
            agg = daily_df.resample(rule).agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum" if "volume" in daily_df.columns else "first",
                    "amount": "sum" if "amount" in daily_df.columns else "first",
                }
            )
            agg = agg.dropna(subset=["close"])
            agg.reset_index(inplace=True)
            df = agg
        else:
            raise
    mask = (df["datetime"] >= pd.to_datetime(start)) & (df["datetime"] <= pd.to_datetime(end))
    return df.loc[mask].reset_index(drop=True)


def load_bt_feed(
    symbol: str,
    start: str,
    end: str,
    frequency: str = "daily",
    adjust: str = "auto",
    prefer_stockdata: bool = True,
    data_root: Optional[str] = None,
    stockdata_root: Optional[str] = None,
    use_real_price: bool | None = None,
    out_path_holder: dict | None = None,
) -> bt.feeds.PandasData:
    """构建 Backtrader 可消费的数据 Feed。"""

    df = load_price_dataframe(
        symbol,
        start,
        end,
        frequency,
        adjust,
        prefer_stockdata,
        data_root,
        stockdata_root,
        use_real_price,
        out_path_holder,
    )
    for col in ("datetime", "open", "high", "low", "close"):
        if col not in df.columns:
            raise ValueError(f"数据缺少必要列: {col}")
    if "volume" not in df.columns:
        df["volume"] = 0
    feed_df = df[["datetime", "open", "high", "low", "close", "volume"]].set_index("datetime")
    return bt.feeds.PandasData(dataname=feed_df)
