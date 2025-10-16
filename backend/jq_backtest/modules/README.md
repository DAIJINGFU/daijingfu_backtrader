# 聚宽回测平台 - 模块总览 🏗️

## 🔄 回测流程与模块对应关系

用户请求 → 1️⃣ 策略编译 → 2️⃣ 数据加载 → 3️⃣ 回测执行 → 4️⃣ 结果处理 → 返回结果
↓ ↓ ↓ ↓  
 1_strategy 2_data 3_backtest 4_result
\_compile \_loader \_engine \_processor

## 📁 模块目录结构

- **[1_strategy_compile/](./1_strategy_compile/)** - 策略编译模块

  - 将用户策略代码编译为 Backtrader 策略类
  - 提供完整聚宽 API 兼容层 (15-20 个函数：数据获取、交易下单、调度器等)

- **[2_data_loader/](./2_data_loader/)** - 数据加载模块

  - 从 CSV 文件加载历史行情数据
  - 分钟数据缓存管理

- **[3_backtest_engine/](./3_backtest_engine/)** - 回测执行模块

  - 回测引擎核心逻辑
  - 定时调度器 (run_daily/weekly 等)

- **[4_result_processor/](./4_result_processor/)** - 结果处理模块

  - 计算回测指标 (收益率、夏普比率等)
  - 生成格式化报告

- **[utils/](./utils/)** - 通用工具模块
  - 数据处理、数学计算等工具函数

## 🚀 快速开始

```python
# 导入所有模块功能
from modules import (
    compile_user_strategy,    # 1️⃣ 策略编译
    BacktestEngine,          # 3️⃣ 回测执行
    format_results           # 4️⃣ 结果处理
)

# 使用示例
strategy_class, jq_state = compile_user_strategy(user_code)
engine = BacktestEngine()
result = engine.run_backtest(symbol, start, end, strategy_class)
formatted_result = format_results(result)
```

## 💡 设计理念

- **编号即流程**：1-4 对应回测的 4 个核心步骤
- **功能单一**：每个模块职责明确，易于理解和维护
- **导入简单**：统一入口，无需记忆复杂的导入路径
- **文档完整**：每个模块都有详细的 README 说明

