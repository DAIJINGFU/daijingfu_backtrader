"""
生成测试用的CSV数据
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path


def generate_daily_data(security: str, start_date: str, end_date: str, output_dir: Path):
    """生成日线测试数据"""
    dates = pd.date_range(start_date, end_date, freq='B')  # 工作日
    n = len(dates)
    
    # 生成模拟价格数据
    base_price = 10.0
    returns = np.random.randn(n) * 0.02  # 2%日波动
    prices = base_price * np.exp(np.cumsum(returns))
    prices = np.maximum(prices, 5.0)  # 最低价5元
    
    df = pd.DataFrame({
        'datetime': dates,
        'open': prices * (1 + np.random.randn(n) * 0.01),
        'high': prices * (1 + abs(np.random.randn(n)) * 0.02),
        'low': prices * (1 - abs(np.random.randn(n)) * 0.02),
        'close': prices,
        'volume': np.random.randint(1000000, 10000000, n),
        'amount': prices * np.random.randint(1000000, 10000000, n),
    })
    
    # 确保 high >= close >= low 和 high >= open >= low
    df['high'] = df[['open', 'close', 'high']].max(axis=1)
    df['low'] = df[['open', 'close', 'low']].min(axis=1)
    
    # Create daily subdirectory for simple format
    daily_dir = output_dir / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    
    # Use correct filename format (without _daily suffix)
    output_path = daily_dir / f"{security}.csv"
    df.to_csv(output_path, index=False)
    print(f"✅ 生成 {output_path}")
    return df


if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "data" / "sample"
    
    # 生成几个测试股票的数据
    print("📊 生成测试数据...")
    generate_daily_data('000001.XSHE', '2020-01-01', '2023-12-31', output_dir)
    generate_daily_data('000002.XSHE', '2020-01-01', '2023-12-31', output_dir)
    generate_daily_data('600000.XSHG', '2020-01-01', '2023-12-31', output_dir)
    generate_daily_data('000300.XSHG', '2020-01-01', '2023-12-31', output_dir)  # 基准
    
    print("✅ 测试数据生成完成！")
    print(f"📁 数据目录: {output_dir}")
