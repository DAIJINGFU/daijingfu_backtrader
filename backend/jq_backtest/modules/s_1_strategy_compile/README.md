# 策略编译模块 (s_1_strategy_compile) 📝

## 📋 功能说明

负责将用户的策略代码编译为 Backtrader 可执行的策略类，同时提供聚宽 API 兼容层。

**核心能力：**

- ✅ 支持标准 Backtrader 策略类
- ✅ 支持聚宽风格策略（initialize + handle_data）
- ✅ 提供完整聚宽 API（20+ 函数）
- ✅ 环境隔离与安全执行
- ✅ T+1、停牌、涨跌停等市场规则

## 📁 模块结构

```
s_1_strategy_compile/
├── __init__.py          # 模块导出
├── compiler.py          # 策略编译器 (498行)
├── jq_api.py            # 聚宽 API 实现 (~300行)
├── jq_models.py         # 聚宽模型类 (~150行)
├── utils.py             # 工具函数 (~50行)
└── README.md            # 本文档
```

### compiler.py - 策略编译核心

编译用户策略代码，支持两种模式：

1. **标准 Backtrader 模式**：用户提供 `UserStrategy` 类
2. **聚宽兼容模式**：用户提供 `initialize()` 和 `handle_data()` 函数

### jq_api.py - 聚宽 API 实现

提供完整的聚宽 API 兼容层（20+ 函数）：

**数据获取 API：**

- `get_price()` - 获取历史行情数据
- `attribute_history()` - 获取指定天数的历史数据
- `history()` - 获取历史数据（别名）
- `get_current_data()` - 获取当前数据快照

**交易下单 API：**

- `order()` - 按股数下单
- `order_value()` - 按金额下单
- `order_target()` - 调仓到目标股数
- `order_target_value()` - 调仓到目标金额
- `order_target_percent()` - 调仓到组合占比

**调度器 API：**

- `run_daily()` - 每日定时执行
- `run_weekly()` - 每周定时执行
- `run_monthly()` - 每月定时执行

**生命周期 API：**

- `before_trading_start()` - 开盘前执行
- `after_trading_end()` - 收盘后执行

**配置 API：**

- `set_benchmark()` - 设置基准指数
- `set_option()` - 设置回测选项
- `set_slippage()` - 设置滑点
- `set_commission()` - 设置佣金

**记录 API：**

- `record()` - 记录自定义数据

### jq_models.py - 聚宽模型类

提供聚宽环境中的核心对象：

- `Portfolio` - 投资组合对象
- `Context` - 策略上下文对象
- `SubPortfolioPosition` - 持仓信息对象
- `PanelDataEmulator` - Panel 数据模拟器

### utils.py - 工具函数

提供通用工具函数：

- `normalize_code()` - 标准化股票代码
- `parse_date()` - 解析日期字符串
- `round_to_price_tick()` - 价格四舍五入到最小价格单位
- `ensure_list()` - 确保返回列表
- `safe_float()` - 安全转换为浮点数
- `merge_position()` - 合并持仓信息

## 🚀 使用示例

### 基础用法

```python
from backend.modules.s_1_strategy_compile import compile_user_strategy

# 用户策略代码
user_code = '''
def initialize(context):
    g.security = '000001.XSHE'
    set_benchmark('000300.XSHE')
    run_daily(buy_stock, '09:30')

def handle_data(context, data):
    pass

def buy_stock(context):
    order_value(g.security, 10000)
'''

# 编译策略
strategy_class, jq_state = compile_user_strategy(user_code)

# strategy_class 可以传递给 Backtrader 执行
# jq_state 包含策略执行所需的状态信息
```

### 统一导入方式

```python
# 方式1：从主模块导入
from backend.modules import compile_user_strategy, get_price, order_value

# 方式2：从子模块导入
from backend.modules.s_1_strategy_compile import (
    compile_user_strategy,
    Portfolio,
    Context,
)
from backend.modules.s_1_strategy_compile.jq_api import (
    get_price,
    order_value,
    run_daily,
)
```

### 聚宽 API 使用示例

```python
# 在策略代码中使用聚宽 API

def initialize(context):
    # 设置基准
    set_benchmark('000300.XSHE')

    # 配置回测选项
    set_option('use_real_price', True)
    set_commission(0.0003)

    # 注册定时任务
    run_daily(rebalance, '09:30')
    run_weekly(adjust_position, '09:30')

def handle_data(context, data):
    # 获取历史数据
    df = get_price('000001.XSHE', count=10, frequency='daily')

    # 获取当前价格
    current = get_current_data()
    price = current['000001.XSHE'].last_price

    # 下单交易
    order_value('000001.XSHE', 10000)
    order_target_percent('000002.XSHE', 0.3)

    # 记录自定义数据
    record(price=price, position=context.portfolio.positions)

def rebalance(context):
    # 调仓逻辑
    pass
```

## 📊 输入输出

### 输入

- **user_code** (str): 用户策略代码字符串

### 输出

- **strategy_class** (type): Backtrader 策略类
- **jq_state** (dict): 聚宽状态字典，包含：
  - `options`: 回测配置选项
  - `schedule`: 调度器任务列表
  - `benchmark`: 基准指数代码
  - `history_df_map`: 历史数据缓存
  - 其他运行时状态

## ✅ 测试验证

模块已通过以下测试：

- ✅ `test_strategy_compile_baseline.py` - 基线测试（20+ API 验证）
- ✅ `test_t1_and_pause.py` - T+1 和停牌测试（5 个场景）
- ✅ `test_scheduler_integration.py` - 调度器集成测试
- ✅ `test_weekly.py` - 周线调度测试
- ✅ `smoke_test.py` - 烟雾测试

所有测试 100% 通过 ✓

## 🔧 技术细节

### 安全机制

- 限制可用的全局变量和内置函数
- 限制可导入的模块（仅允许 numpy, pandas 等安全模块）
- 使用 `exec()` 在隔离的命名空间中执行用户代码

### 市场规则

- **T+1 制度**：当日买入的股票次日才能卖出
- **停牌检测**：自动检测停牌日期，阻止交易
- **涨跌停限制**：限制价格在涨跌停范围内
- **价格取整**：自动四舍五入到最小价格单位（0.01）

### 性能优化

- 历史数据缓存（避免重复加载）
- 分钟数据聚合缓存
- 持仓信息快照机制

## 🎓 相关文档

- [模块化重构实施方案](../../../docs/模块化重构实施方案-v2.md)
- [重构方案优化总结](../../../docs/重构方案优化总结.md)
- [聚宽 API 文档](https://www.joinquant.com/help/api/help)

