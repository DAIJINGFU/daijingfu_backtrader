"""聚宽环境模拟 - Portfolio, Context 等类定义

这个模块提供聚宽平台的核心对象模拟，用于策略执行时的上下文环境。
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional
import types

from .utils import merge_position

if TYPE_CHECKING:
    import backtrader as bt


__all__ = [
    "SubPortfolioPosition",
    "Portfolio",
    "Context",
    "PanelDataEmulator",
    "CurrentSnapshot",
    "CurrentDataProxy",
    "GlobalVariableContainer",
    "JQLogger",
]


class SubPortfolioPosition:
    """持仓信息对象 - 模拟聚宽的持仓数据结构"""
    
    def __init__(self, closeable_amount: int = 0, total_amount: int = 0):
        self.closeable_amount = closeable_amount  # 可卖数量
        self.total_amount = total_amount  # 总持仓数量
    
    def __repr__(self):
        return f"Position(closeable={self.closeable_amount}, total={self.total_amount})"


class Portfolio:
    """投资组合对象 - 模拟聚宽的 context.portfolio
    
    提供账户资金和持仓信息的查询接口。
    """
    
    def __init__(self, broker, jq_state: Dict[str, Any]):
        self._broker = broker
        self._jq_state = jq_state
    
    @property
    def available_cash(self) -> float:
        """可用资金"""
        return self._broker.getcash()
    
    @property
    def total_value(self) -> float:
        """总资产价值"""
        return self._broker.getvalue()
    
    @property
    def positions(self) -> Dict[str, SubPortfolioPosition]:
        """持仓字典 {股票代码: Position对象}
        
        实现T+1制度：可卖数量 = 总持仓 - 当日买入数量
        """
        strategy_module = self._jq_state.get('_strategy_instance')
        snapshot = merge_position(strategy_module, self._jq_state)
        if not snapshot:
            return {}

        result: Dict[str, SubPortfolioPosition] = {}
        for symbol, info in snapshot.items():
            if not isinstance(info, dict):
                continue
            try:
                total_amount = int(info.get('total_amount', 0) or 0)
                closeable = int(info.get('closeable_amount', 0) or 0)
            except Exception:
                continue
            if total_amount == 0:
                continue
            result[str(symbol)] = SubPortfolioPosition(
                closeable_amount=max(0, closeable),
                total_amount=total_amount,
            )
        return result
    
    @property
    def positions_value(self) -> float:
        """持仓总市值"""
        return self.total_value - self.available_cash


class Context:
    """策略上下文对象 - 模拟聚宽的 context
    
    提供策略运行时的环境信息，包括投资组合、当前时间等。
    """
    
    def __init__(self, broker, jq_state: Dict[str, Any], bt_strategy):
        self.portfolio = Portfolio(broker, jq_state)
        self._jq_state = jq_state
        self._bt_strategy = bt_strategy
    
    @property
    def current_dt(self):
        """返回当前日期时间对象"""
        try:
            import datetime as dt_module
            import backtrader as bt
            
            current_dt_str = self._jq_state.get('current_dt', '')
            if current_dt_str:
                # current_dt 格式为 "YYYY-MM-DD HH:MM:SS"
                return dt_module.datetime.strptime(current_dt_str, '%Y-%m-%d %H:%M:%S')
            else:
                # 回退到当前bar的时间
                if hasattr(self._bt_strategy, 'data') and hasattr(self._bt_strategy.data, 'datetime'):
                    return bt.num2date(self._bt_strategy.data.datetime[0])
                return dt_module.datetime.now()
        except Exception:
            import datetime as dt_module
            return dt_module.datetime.now()
    
    def __repr__(self):
        return f"Context(dt={self.current_dt}, cash={self.portfolio.available_cash:.2f})"


class PanelDataEmulator:
    """Panel数据模拟器 - 模拟聚宽的 Panel 数据结构
    
    用于 get_price(panel=True) 的返回值。
    支持 panel['open'] 获取 DataFrame (行=日期, 列=证券代码)。
    """
    
    def __init__(self, data_map: Dict[str, Any], use_fields: list):
        """初始化Panel数据模拟器
        
        参数:
            data_map: 字典 {证券代码 -> DataFrame}
            use_fields: 需要构造的字段列表
        """
        import pandas as pd
        
        # 统一日期集合（按升序排列）
        all_dates = sorted({d for df in data_map.values() for d in df.index})
        
        self._fields = set()
        self._dates = all_dates
        self._secs = list(data_map.keys())
        self._cube = {}  # 存储 {field: DataFrame(index=dates, columns=secs)}
        
        # 为每个字段构建 DataFrame 矩阵
        for field in use_fields:
            mat = pd.DataFrame(index=all_dates, columns=self._secs, dtype=float)
            for sec, df in data_map.items():
                if field in df.columns:
                    mat.loc[df.index, sec] = df[field]
            self._cube[field] = mat
            self._fields.add(field)
    
    def __getitem__(self, field: str):
        """获取指定字段的 DataFrame
        
        参数:
            field: 字段名如 'open', 'close', 'high', 'low', 'volume'
            
        返回:
            DataFrame，索引为日期，列为证券代码
        """
        import pandas as pd
        return self._cube.get(field, pd.DataFrame())
    
    @property
    def fields(self):
        """返回所有可用字段列表"""
        return list(self._fields)
    
    @property
    def symbols(self):
        """返回所有证券代码列表"""
        return list(self._secs)
    
    def __repr__(self):
        return f"PanelEmu(symbols={len(self._secs)}, fields={self.fields})"


# ═══════════════════════════════════════════════════════════
# 当前数据快照类（从 jq_api.py 迁移）
# ═══════════════════════════════════════════════════════════


class CurrentSnapshot:
    """当前数据快照对象 - 字典/属性双访问模式
    
    用于 get_current_data() 返回的单个证券快照。
    支持 snapshot.last_price 或 snapshot['last_price'] 两种访问方式。
    """

    __slots__ = ("_payload",)

    def __init__(self, payload: Dict[str, Any]) -> None:
        self._payload = payload

    def __getattr__(self, item: str) -> Any:
        if item in self._payload:
            return self._payload[item]
        raise AttributeError(item)

    def __getitem__(self, item: str) -> Any:
        return self._payload.get(item)

    def get(self, item: str, default: Any = None) -> Any:
        return self._payload.get(item, default)

    def to_dict(self) -> Dict[str, Any]:
        return dict(self._payload)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        lp = self._payload.get("last_price")
        paused = self._payload.get("is_paused")
        return f"CurrentSnapshot(last_price={lp!r}, paused={paused})"


class CurrentDataProxy:
    """当前数据代理对象 - 按需构建快照的容器
    
    用于 get_current_data() 的返回值。
    支持字典式访问：current_data[security] 返回 CurrentSnapshot。
    """

    __slots__ = ("_state", "_cache")

    def __init__(self, state: Dict[str, Any], cache: Dict[str, Any]) -> None:
        self._state = state
        self._cache = cache

    def _snapshot_store(self) -> Dict[str, CurrentSnapshot]:
        """获取快照存储字典"""
        store = self._cache.get("__snapshots__")
        if not isinstance(store, dict):
            store = {}
            self._cache["__snapshots__"] = store
        return store

    def _available_keys(self) -> set[str]:
        """从状态中获取所有可用的证券代码键"""
        from .utils import normalize_security_key
        
        available: set[str] = set(self._snapshot_store().keys())

        def _maybe_add(value: Any) -> None:
            key = normalize_security_key(value)
            if key:
                available.add(key)

        hist_map = self._state.get("history_df_map")
        if isinstance(hist_map, dict):
            for key in hist_map.keys():
                _maybe_add(key)

        symbol_map = self._state.get("symbol_file_map")
        if isinstance(symbol_map, dict):
            for key in symbol_map.keys():
                _maybe_add(key)

        universe = self._state.get("universe")
        if isinstance(universe, (list, tuple, set)):
            for item in universe:
                _maybe_add(item)

        g_obj = self._state.get("g")
        if g_obj is not None:
            _maybe_add(getattr(g_obj, "security", None))

        return available

    def __getitem__(self, security: Any) -> CurrentSnapshot:
        """获取证券的当前数据快照"""
        from .utils import normalize_security_key, build_snapshot_for_security
        
        key = normalize_security_key(security)
        if not key:
            raise KeyError(f"invalid security {security!r}")
        if key not in self._available_keys():
            raise KeyError(f"security {security!r} not available")

        store = self._snapshot_store()
        snap = store.get(key)
        if snap is None:
            payload = build_snapshot_for_security(self._state, key)
            snap = CurrentSnapshot(payload)
            store[key] = snap
        return snap

    def get(self, security: Any, default: Any = None) -> Any:
        """安全获取证券快照，失败时返回默认值"""
        try:
            return self[security]
        except KeyError:
            return default

    def __contains__(self, security: Any) -> bool:  # pragma: no cover - 委托方法
        from .utils import normalize_security_key
        
        key = normalize_security_key(security)
        if not key:
            return False
        return key in self._available_keys()

    def keys(self):  # pragma: no cover - 迭代辅助
        """返回所有可用证券代码的排序列表"""
        return sorted(self._available_keys())

    def values(self):  # pragma: no cover - 迭代辅助
        """返回所有证券快照的列表"""
        return [self[key] for key in self.keys()]

    def items(self):  # pragma: no cover - 迭代辅助
        """返回所有证券代码和快照的配对列表"""
        return [(key, self[key]) for key in self.keys()]

    def __iter__(self):  # pragma: no cover - 迭代辅助
        """迭代所有证券代码"""
        for key in self.keys():
            yield key

    def __len__(self) -> int:  # pragma: no cover - 简单实现
        """返回可用证券的数量"""
        return len(self._available_keys())

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        return f"CurrentDataProxy(size={len(self)})"


# ═══════════════════════════════════════════════════════════
# 环境辅助类
# ═══════════════════════════════════════════════════════════


class GlobalVariableContainer:
    """
    用户全局变量容器（g 对象）。

    在聚宽策略中，用户可以使用 context.g 或直接使用 g 来存储自定义数据。
    这是一个简单的容器类，支持动态属性赋值。

    示例:
        >>> g = GlobalVariableContainer()
        >>> g.my_var = 100
        >>> g.stock_list = ['000001.XSHE', '600000.XSHG']
    """
    pass  # pragma: no cover - trivial container


class JQLogger:
    """
    聚宽兼容的日志对象。

    提供类似 logging.Logger 的接口，但输出到 jq_state["log"] 列表中。
    在热身阶段 (in_warmup=True) 会自动抑制日志输出。

    属性:
        _jq_state: 聚宽状态字典的引用

    设计说明:
        - 这是聚宽环境特有的日志模型，不是通用日志工具
        - 与 jq_state 紧密绑定，是聚宽状态管理的一部分
        - 日志数据存储在 jq_state["log"] 列表中
    """

    def __init__(self, jq_state: Dict[str, Any]):
        """
        初始化日志对象。

        参数:
            jq_state: 聚宽状态字典，必须包含 'log' 和 'in_warmup' 字段
        """
        self._jq_state = jq_state

    def info(self, msg: Any) -> None:
        """
        记录信息级别的日志。

        参数:
            msg: 要记录的消息（会自动转换为字符串）

        行为:
            - 日志格式: "{时间} - INFO - {消息}"
            - 多行消息会自动缩进（第2行开始前置4个空格）
            - 热身阶段 (in_warmup=True) 不输出日志
            - 同时输出到 jq_state["log"] 列表和 print()

        示例:
            >>> jq_state = {"log": [], "in_warmup": False, "current_dt": "2025-10-14 09:30:00"}
            >>> logger = JQLogger(jq_state)
            >>> logger.info("策略初始化完成")
            2025-10-14 09:30:00 - INFO - 策略初始化完成
        """
        # 热身阶段跳过日志
        if self._jq_state.get("in_warmup"):
            return

        # 获取当前时间
        try:
            import pandas as pd
            dt_value = self._jq_state.get("current_dt") or pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            dt_value = "0000-00-00 00:00:00"

        # 格式化消息（支持多行）
        header = f"{dt_value} - INFO - "
        lines = str(msg).splitlines() or [""]
        formatted = "\n".join([header + lines[0]] + ["    " + ln for ln in lines[1:]])

        # 输出到日志列表和控制台
        self._jq_state["log"].append(formatted)
        print(formatted)
