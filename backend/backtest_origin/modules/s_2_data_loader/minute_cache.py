"""分钟数据缓存管理与分钟级行情聚合工具。"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from . import csv_loader

__all__ = [
    "CacheConfig",
    "MinuteAggregationCache",
    "aggregate_minute_dataframe",
    "default_cache_dir",
    "build_cache_key",
    "get_source_mtime",
]


@dataclass
class CacheConfig:
    """缓存配置参数。"""

    persist: bool
    cache_dir: Path
    log: Callable[[str], None]


class MinuteAggregationCache:
    """负责分钟聚合结果的加载与保存。"""

    META_SUFFIX = ".meta.json"
    DATA_SUFFIX = ".parquet"

    def __init__(self, config: CacheConfig) -> None:
        self._config = config
        if self._config.persist:
            self._config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_status: Optional[str] = None
        self._last_rows: Optional[int] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def load(self, key: str, source_mtime: Optional[float]) -> Optional[pd.DataFrame]:
        """尝试从本地缓存加载聚合结果。"""

        self._last_rows = None
        self._last_error = None
        if not self._config.persist:
            self._last_status = "disabled"
            return None

        data_path = self._config.cache_dir / f"{key}{self.DATA_SUFFIX}"
        meta_path = self._config.cache_dir / f"{key}{self.META_SUFFIX}"
        if not data_path.exists() or not meta_path.exists():
            self._last_status = "miss"
            return None

        try:
            with meta_path.open("r", encoding="utf-8") as fh:
                meta = json.load(fh)
        except Exception as exc:  # pragma: no cover - 元数据损坏
            self._last_status = "meta_error"
            self._last_error = f"meta_read_error:{type(exc).__name__}:{exc}"
            self._config.log(f"[minute_cache] meta_read_error key={key} err={type(exc).__name__}:{exc}")
            return None

        cached_mtime = meta.get("source_mtime")
        if source_mtime is not None and cached_mtime is not None:
            if abs(source_mtime - cached_mtime) > 1e-6:
                self._last_status = "mismatch"
                self._config.log(
                    f"[minute_cache] source_mtime_mismatch key={key} cached={cached_mtime} current={source_mtime}"
                )
                return None

        try:
            df = pd.read_parquet(data_path)
            self._last_rows = len(df)
            self._last_status = "hit"
            self._config.log(f"[minute_cache] hit key={key} rows={len(df)} path={data_path}")
            return df
        except Exception as exc:  # pragma: no cover - parquet 读取异常
            self._last_status = "load_error"
            self._last_error = f"load_error:{type(exc).__name__}:{exc}"
            self._config.log(f"[minute_cache] load_error key={key} err={type(exc).__name__}:{exc}")
            return None

    def save(self, key: str, df: pd.DataFrame, source_mtime: Optional[float]) -> None:
        """将聚合结果写入缓存目录。"""

        if not self._config.persist:
            return
        data_path = self._config.cache_dir / f"{key}{self.DATA_SUFFIX}"
        meta_path = self._config.cache_dir / f"{key}{self.META_SUFFIX}"
        self._last_error = None
        try:
            df.to_parquet(data_path, index=False)
            meta = {
                "source_mtime": source_mtime,
                "rows": int(len(df)),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            self._config.log(f"[minute_cache] persisted key={key} rows={len(df)} path={data_path}")
            self._last_status = "saved"
            self._last_rows = len(df)
        except Exception as exc:  # pragma: no cover - 写入异常
            self._config.log(f"[minute_cache] persist_error key={key} err={type(exc).__name__}:{exc}")
            self._last_status = "persist_error"
            self._last_error = f"persist_error:{type(exc).__name__}:{exc}"

    @property
    def last_status(self) -> Optional[str]:
        return self._last_status

    @property
    def last_rows(self) -> Optional[int]:
        return self._last_rows

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------


def aggregate_minute_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """将分钟级行情聚合为日线结果。"""

    if df.empty:
        return df.copy()
    if "datetime" not in df.columns:
        raise ValueError("minute dataframe 缺少 datetime 列")

    working = df.copy()
    working["datetime"] = pd.to_datetime(working["datetime"], errors="coerce")
    working = working.dropna(subset=["datetime"])
    working["date"] = working["datetime"].dt.date

    agg_map: dict[str, str] = {}
    for col in ("open", "close", "high", "low", "volume", "amount"):
        if col not in working.columns:
            continue
        if col == "open":
            agg_map[col] = "first"
        elif col == "close":
            agg_map[col] = "last"
        elif col == "high":
            agg_map[col] = "max"
        elif col == "low":
            agg_map[col] = "min"
        else:
            agg_map[col] = "sum"

    aggregated = working.groupby("date", as_index=False).agg(agg_map)
    aggregated["datetime"] = pd.to_datetime(aggregated["date"])
    ordered_cols = ["datetime", "open", "high", "low", "close", "volume", "amount"]
    cols = [c for c in ordered_cols if c in aggregated.columns]
    remaining = [c for c in aggregated.columns if c not in cols]
    aggregated = aggregated[cols + remaining]
    aggregated = aggregated.sort_values("datetime").reset_index(drop=True)
    aggregated["date"] = aggregated["datetime"].dt.date
    return aggregated


def default_cache_dir() -> Path:
    """返回默认缓存目录。"""

    return Path(__file__).resolve().parents[2] / "cache" / "minute_daily"


def build_cache_key(symbol: str, adjust: str | None, use_real_price: bool | None) -> str:
    normalized = csv_loader.normalize_symbol(symbol)
    adjust_part = (adjust or "auto").lower()
    real_part = "real" if use_real_price else "adj"
    return f"{normalized}_{adjust_part}_{real_part}"


def get_source_mtime(path: Optional[str]) -> Optional[float]:
    if not path:
        return None
    try:
        return os.path.getmtime(path)
    except OSError:
        return None
