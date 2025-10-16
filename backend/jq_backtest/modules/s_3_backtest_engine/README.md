# 第 3 步：回测执行模块 ⚙️

## 功能说明

回测引擎核心，整合策略、数据、调度器，执行完整的回测流程。

## 核心文件

- `engine.py` - 回测引擎主逻辑
- `executor.py` - 策略执行器
- `scheduler/` - 定时调度器 (run_daily/weekly 等)

## 使用示例

```python
from modules.3_backtest_engine.engine import BacktestEngine
engine = BacktestEngine()
result = engine.run_backtest(symbol, start, end, strategy_class)
```

## 输入输出

- 输入：策略类、数据、回测参数
- 输出：回测原始结果

