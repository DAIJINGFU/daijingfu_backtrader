# API规范文档 - JoinQuant回测引擎

## 📋 概述

本文档定义了JoinQuant兼容回测引擎的完整API规范。实习生必须严格遵循此规范进行开发，以确保与主系统的兼容性。

---

## 🎯 核心接口

### 1. BacktestEngine.run_backtest()

**功能**: 运行完整的回测流程

#### 输入参数

```python
def run_backtest(
    strategy_code: str,              # 策略代码字符串
    start_date: datetime,            # 回测开始日期
    end_date: datetime,              # 回测结束日期
    initial_cash: float = 1000000,   # 初始资金（默认100万）
    securities: Optional[List[str]] = None,  # 证券列表（可选）
    commission: Optional[float] = None,      # 手续费率（可选）
    stamp_duty: Optional[float] = None,      # 印花税率（可选）
    freq: str = 'daily',             # 数据频率：'daily' 或 'minute'
    fq: str = 'pre'                  # 复权方式：'pre', 'post', 'none'
) -> Dict[str, Any]:
```

#### 输出格式

**必需字段**:

```python
{
    # 基础信息
    "backtest_id": "unique-uuid-string",
    "status": "completed",  # 'completed', 'failed', 'running'
    
    # 资金信息
    "initial_cash": 1000000.0,
    "final_value": 1150000.0,
    
    # 收益指标
    "total_return": 0.15,  # 15%总收益
    "annualized_return": 0.12,  # 12%年化收益
    
    # 风险指标
    "annualized_volatility": 0.18,  # 年化波动率
    "sharpe_ratio": 1.5,  # 夏普比率
    "sortino_ratio": 2.0,  # 索提诺比率
    "max_drawdown": -0.08,  # 最大回撤 -8%
    "calmar_ratio": 1.2,  # 卡玛比率
    
    # 交易统计
    "total_trades": 50,
    "winning_trades": 32,
    "losing_trades": 18,
    "win_rate": 0.64,  # 胜率
    "profit_factor": 2.1,  # 盈亏比
    
    # 时间序列数据
    "equity_curve": [
        {"datetime": "2023-01-01T00:00:00", "value": 1000000.0},
        {"datetime": "2023-01-02T00:00:00", "value": 1001500.0},
        # ...
    ],
    
    "daily_returns": [
        {"datetime": "2023-01-01T00:00:00", "return": 0.0015},
        {"datetime": "2023-01-02T00:00:00", "return": 0.0023},
        # ...
    ],
    
    "drawdown_curve": [
        {"datetime": "2023-01-01T00:00:00", "value": 0.0},
        {"datetime": "2023-01-02T00:00:00", "value": -0.02},
        # ...
    ],
    
    "positions": [
        {
            "datetime": "2023-01-01T00:00:00",
            "security": "000001.XSHE",
            "amount": 100,
            "price": 10.5,
            "value": 1050.0
        },
        # ...
    ],
    
    "trades": [
        {
            "datetime": "2023-01-01T09:30:00",
            "instrument": "000001.XSHE",
            "side": "buy",  # 'buy' or 'sell'
            "amount": 100,
            "price": 10.5,
            "commission": 5.0,
            "value": 1050.0
        },
        # ...
    ],
    
    # 回测日期
    "start_date": "2023-01-01",
    "end_date": "2023-12-31",
    "created_at": "2024-01-15T10:30:00",
    
    # 可选：基准对比
    "benchmark": "000300.XSHG",
    "benchmark_curve": [...],  # 同equity_curve格式
    "benchmark_total_return": 0.10,
    "benchmark_sharpe": 1.2,
    
    # 可选：数据覆盖信息
    "actual_start_date": "2023-01-04",  # 实际数据开始日期
    "actual_end_date": "2023-12-29",    # 实际数据结束日期
    "bars_loaded": 245,                 # 加载的K线数量
    
    # 错误信息（如果失败）
    "error": null  # 或错误消息字符串
}
```

---

## 📊 指标计算公式

### 1. 总收益率 (Total Return)

```python
total_return = (final_value - initial_cash) / initial_cash
```

### 2. 年化收益率 (Annualized Return)

```python
days = (end_date - start_date).days
years = days / 365.0
annualized_return = (final_value / initial_cash) ** (1 / years) - 1
```

### 3. 年化波动率 (Annualized Volatility)

```python
daily_returns = equity_curve.pct_change()
annualized_volatility = daily_returns.std() * sqrt(252)
```

### 4. 夏普比率 (Sharpe Ratio)

```python
sharpe_ratio = (annualized_return - risk_free_rate) / annualized_volatility
# 假设无风险利率为0
sharpe_ratio = annualized_return / annualized_volatility
```

### 5. 最大回撤 (Max Drawdown)

```python
peak = equity_curve.expanding().max()
drawdown = (equity_curve - peak) / peak
max_drawdown = drawdown.min()
```

### 6. 索提诺比率 (Sortino Ratio)

```python
downside_returns = daily_returns[daily_returns < 0]
downside_deviation = downside_returns.std() * sqrt(252)
sortino_ratio = annualized_return / downside_deviation
```

### 7. 卡玛比率 (Calmar Ratio)

```python
calmar_ratio = annualized_return / abs(max_drawdown)
```

### 8. 胜率 (Win Rate)

```python
win_rate = winning_trades / total_trades
```

### 9. 盈亏比 (Profit Factor)

```python
profit_factor = total_profit / abs(total_loss)
```

---

## 🔌 JoinQuant API规范

### 策略代码格式

实习生的引擎必须能够解析和执行以下格式的策略代码：

```python
def initialize(context):
    """
    策略初始化函数
    在回测开始时调用一次
    """
    # 设置全局变量
    g.security = '000001.XSHE'
    g.trade_count = 0
    
    # 设置基准
    set_benchmark('000300.XSHG')
    
    # 设置交易成本
    set_order_cost(OrderCost(
        open_tax=0,
        close_tax=0.001,
        open_commission=0.0003,
        close_commission=0.0003,
        min_commission=5
    ))
    
    # 注册定时任务
    run_daily(market_open, time='09:30')
    run_weekly(rebalance, weekday=1)

def handle_data(context, data):
    """
    主策略函数
    每个交易日/分钟调用一次
    """
    # 获取当前价格
    price = data[g.security].close
    
    # 获取持仓
    position = context.portfolio.positions[g.security]
    
    # 交易逻辑
    if position.amount == 0:
        if price > 10:
            order(g.security, 100)
    else:
        if price < 9:
            order_target(g.security, 0)

def before_trading_start(context):
    """盘前函数（可选）"""
    pass

def after_trading_end(context):
    """盘后函数（可选）"""
    pass

def market_open(context):
    """定时任务函数示例"""
    pass
```

### 必须支持的API

#### 配置API

```python
set_benchmark(code: str) -> None
    """设置基准指数"""

set_order_cost(cost: OrderCost) -> None
    """设置交易成本"""

set_option(key: str, value: Any) -> None
    """设置其他选项"""
```

#### 交易API

```python
order(security: str, amount: int) -> Order
    """按股数下单"""

order_target(security: str, amount: int) -> Order
    """调整至目标持仓数量"""

order_value(security: str, value: float) -> Order
    """按金额下单"""

order_target_value(security: str, value: float) -> Order
    """调整至目标持仓金额"""

get_open_orders(security: Optional[str] = None) -> List[Order]
    """获取未成交订单"""

cancel_order(order: Order) -> bool
    """取消订单"""
```

#### 数据API

```python
history(
    count: int,
    unit: str,  # '1d', '1m'
    field: str,  # 'close', 'open', 'high', 'low', 'volume'
    security_list: List[str],
    fq: str = 'pre'
) -> pd.DataFrame
    """获取历史数据（多证券）"""

attribute_history(
    security: str,
    count: int,
    unit: str = '1d',
    fields: List[str] = ['close'],
    fq: str = 'pre'
) -> pd.DataFrame
    """获取历史数据（单证券）"""

get_price(
    security: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    frequency: str = 'daily',
    fields: List[str] = None,
    fq: str = 'pre'
) -> pd.DataFrame
    """获取价格数据"""

# 当前bar数据访问
data[security].close  # 收盘价
data[security].open   # 开盘价
data[security].high   # 最高价
data[security].low    # 最低价
data[security].volume # 成交量
```

#### 定时任务API

```python
run_daily(func: Callable, time: str) -> None
    """每日定时执行"""

run_weekly(func: Callable, weekday: int, time: str = '09:30') -> None
    """每周定时执行"""

run_monthly(func: Callable, monthday: int, time: str = '09:30') -> None
    """每月定时执行"""
```

#### 对象模型

**Context对象**:
```python
context.current_dt         # 当前时间
context.portfolio          # 投资组合
context.portfolio.cash     # 可用资金
context.portfolio.positions  # 持仓字典
context.portfolio.total_value  # 总资产
```

**Portfolio对象**:
```python
portfolio.cash              # 可用资金
portfolio.total_value       # 总资产
portfolio.positions         # 持仓字典 {security: Position}
portfolio.starting_cash     # 初始资金
portfolio.available_cash    # 可用资金
```

**Position对象**:
```python
position.security          # 证券代码
position.amount            # 持仓数量
position.price             # 持仓成本价
position.value             # 持仓市值
position.pnl               # 盈亏
```

**Order对象**:
```python
order.security            # 证券代码
order.amount              # 订单数量
order.status              # 订单状态
order.filled              # 已成交数量
order.price               # 订单价格
```

---

## 🧪 测试要求

### 1. 单元测试

每个核心函数必须有对应的单元测试：

```python
# test_engine.py
def test_parse_strategy_code():
    """测试策略代码解析"""
    code = "def initialize(context): pass"
    engine = JQBacktestEngine()
    funcs = engine._parse_strategy_code(code)
    assert 'initialize' in funcs

def test_calculate_metrics():
    """测试指标计算"""
    equity_curve = [...]
    metrics = engine._calculate_metrics(equity_curve)
    assert 'sharpe_ratio' in metrics
    assert isinstance(metrics['sharpe_ratio'], float)
```

### 2. API兼容性测试

```python
def test_trading_api_compatibility():
    """测试所有交易API"""
    strategy = """
    def initialize(context): pass
    def handle_data(context, data):
        order('000001.XSHE', 100)
        order_target('000001.XSHE', 200)
        order_value('000001.XSHE', 10000)
        order_target_value('000001.XSHE', 50000)
        cancel_order(order_list[0])
        get_open_orders('000001.XSHE')
    """
    result = run_backtest(strategy, ...)
    assert result['status'] == 'completed'
```

### 3. 结果格式测试

```python
def test_result_format():
    """验证结果格式完整性"""
    result = run_backtest(...)
    
    required_fields = [
        'backtest_id', 'status', 'total_return', 
        'sharpe_ratio', 'equity_curve', 'trades'
    ]
    
    for field in required_fields:
        assert field in result
        assert result[field] is not None
```

### 4. 性能测试

```python
def test_performance():
    """性能基准测试"""
    import time
    
    start = time.time()
    result = run_backtest(
        strategy_code=strategy,
        start_date=datetime(2020, 1, 1),
        end_date=datetime(2023, 12, 31)
    )
    elapsed = time.time() - start
    
    # 3年日线回测应在30秒内完成
    assert elapsed < 30
```

---

## 📏 代码规范

### 1. 代码风格

- 遵循 PEP 8
- 使用类型注解
- 函数必须有docstring

```python
def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0
) -> float:
    """
    计算夏普比率
    
    Args:
        returns: 日收益率序列
        risk_free_rate: 无风险利率（默认0）
    
    Returns:
        夏普比率
    """
    # 实现代码
    pass
```

### 2. 日志规范

使用loguru记录关键操作：

```python
from loguru import logger

logger.info(f"Starting backtest from {start_date} to {end_date}")
logger.debug(f"Loaded {len(data)} bars for {security}")
logger.warning(f"Order rejected: insufficient cash")
logger.error(f"Failed to load data for {security}: {error}")
```

### 3. 异常处理

```python
try:
    result = engine.run_backtest(...)
except ValueError as e:
    logger.error(f"Invalid parameter: {e}")
    return {"status": "failed", "error": str(e)}
except Exception as e:
    logger.exception("Unexpected error in backtest")
    return {"status": "failed", "error": str(e)}
```

---

## ✅ 验收检查清单

### 功能完整性
- [ ] 支持所有必需的JoinQuant API
- [ ] 正确解析策略代码
- [ ] 正确执行交易逻辑
- [ ] 正确计算所有指标
- [ ] 支持日线和分钟线数据
- [ ] 支持复权数据处理

### 结果准确性
- [ ] 收益率计算正确
- [ ] 夏普比率计算正确
- [ ] 回撤计算正确
- [ ] 交易记录完整
- [ ] 持仓跟踪准确

### 性能要求
- [ ] 3年日线回测 < 30秒
- [ ] 1年分钟线回测 < 2分钟
- [ ] 内存使用合理（< 2GB）

### 代码质量
- [ ] 测试覆盖率 > 80%
- [ ] 无明显性能瓶颈
- [ ] 代码符合规范
- [ ] 文档完整

---

## 📚 参考资源

### JoinQuant官方文档
- API文档: https://www.joinquant.com/help/api/
- 研究文档: https://www.joinquant.com/help/research/

### Backtrader文档
- 官方文档: https://www.backtrader.com/docu/
- 策略示例: https://www.backtrader.com/docu/strategy/

### Python库
- Pandas: https://pandas.pydata.org/docs/
- NumPy: https://numpy.org/doc/

---

## 🆘 常见问题

### Q1: 如何处理停牌股票？
A: 在数据中标记停牌，交易API应拒绝对停牌股票的操作。

### Q2: 如何处理涨跌停？
A: 实现交易规则检查，涨停不能买入，跌停不能卖出。

### Q3: 订单成交价格如何确定？
A: 默认使用当前bar的收盘价成交（回测模式）。

### Q4: 如何处理不足100股的情况？
A: A股必须是100股的整数倍，自动向下取整。

### Q5: 手续费如何计算？
A: 根据OrderCost配置，买入收取佣金，卖出收取佣金+印花税。

---

## 联系支持

有问题请：
1. 查看本文档
2. 查看示例代码
3. 提交Issue到Git仓库
4. 联系导师
