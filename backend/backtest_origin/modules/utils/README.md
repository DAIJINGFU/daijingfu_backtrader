# 工具模块 🔧

## 功能说明

提供各种通用工具函数，供其他模块使用。

## 核心文件

- `data_utils.py` - 数据处理工具
- `math_utils.py` - 数学计算工具
- `validation.py` - 验证工具

## 使用示例

```python
from modules.utils.data_utils import round_to_tick
price = round_to_tick(10.567, 0.01)  # 10.57
```
