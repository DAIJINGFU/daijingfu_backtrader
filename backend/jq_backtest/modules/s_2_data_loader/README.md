# 第 2 步：数据加载模块 📊

## 功能说明

负责从各种数据源加载历史行情数据，支持日线和分钟线数据。

## 核心文件

- `data_pipeline.py` - 数据加载流水线
- `csv_loader.py` - CSV 文件数据加载器
- `minute_cache.py` - 分钟数据缓存管理
- `market_data.py` - 市场数据处理工具

## 使用示例

```python
from modules.2_data_loader.csv_loader import load_csv_data
data = load_csv_data('000001', '2023-01-01', '2023-12-31')
```

## 输入输出

- 输入：股票代码、开始日期、结束日期
- 输出：pandas.DataFrame 格式的历史数据

