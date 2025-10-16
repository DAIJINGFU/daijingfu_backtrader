"""管线默认选项集中管理。

P3-1 目标：将日线与分线（分钟）回测使用的默认选项集中到统一配置，
避免在各个 Pipeline 中散落大量 ``setdefault`` 调用，便于后续扩展与测试。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, MutableMapping, Optional


@dataclass(frozen=True)
class PipelineOptionProfile:
    """描述某条回测管线的默认选项集合。"""

    name: str
    base_defaults: Mapping[str, Any] = field(default_factory=dict)
    frequency_defaults: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)

    def apply(self, options: MutableMapping[str, Any], frequency: Optional[str] = None) -> None:
        """将默认值写入 ``options``，仅在键不存在时生效。"""

        for key, value in self.base_defaults.items():
            options.setdefault(key, value)

        if not frequency:
            return

        freq_key = frequency.lower()
        freq_defaults = self.frequency_defaults.get(freq_key)
        if not freq_defaults:
            return

        for key, value in freq_defaults.items():
            options.setdefault(key, value)


_intraday_profile = PipelineOptionProfile(
    name="intraday",
    base_defaults={
        "bt_runonce": True,
        "bt_exactbars": 1,
        "persist_minute_agg": False,
        "minute_cache_dir": None,
    },
    frequency_defaults={
        "1min": {
            "minute_default_lookback_days": 10,
            "minute_bars_per_day": 240,
        }
    },
)

_daily_profile = PipelineOptionProfile(
    name="daily",
    base_defaults={
        "bt_runonce": False,
        "bt_exactbars": 0,
        "daily_default_lookback_days": 250,
        "weekly_default_lookback_weeks": 60,
        "monthly_default_lookback_months": 36,
    },
    frequency_defaults={
        "weekly": {
            "weekly_default_lookback_weeks": 60,
        },
        "monthly": {
            "monthly_default_lookback_months": 36,
        },
    },
)

_PROFILE_REGISTRY: Dict[str, PipelineOptionProfile] = {
    _intraday_profile.name: _intraday_profile,
    _daily_profile.name: _daily_profile,
}


def ensure_pipeline_defaults(jq_state: MutableMapping[str, Any], profile_name: str, frequency: Optional[str]) -> MutableMapping[str, Any]:
    """确保 ``jq_state['options']`` 拥有指定管线的默认选项。"""

    options = jq_state.setdefault("options", {})
    profile = _PROFILE_REGISTRY.get(profile_name)
    if profile is None:
        return options

    profile.apply(options, frequency)
    return options


__all__ = [
    "PipelineOptionProfile",
    "ensure_pipeline_defaults",
]
