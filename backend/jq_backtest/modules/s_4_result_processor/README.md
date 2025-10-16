# 第 4 步：结果处理模块 📈

## 功能说明

处理回测原始结果，计算各项指标，生成可视化报告。

## 核心文件

- `analyzer.py` - 回测结果分析器
- `formatter.py` - 结果格式化器
- `reporter.py` - 报告生成器

## 使用示例

```python
from modules.4_result_processor.formatter import format_results
formatted_result = format_results(raw_backtest_result)
```

## 输入输出

- 输入：回测原始结果
- 输出：包含收益率、夏普比率、最大回撤等的格式化结果

