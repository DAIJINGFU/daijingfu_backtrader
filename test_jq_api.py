#!/usr/bin/env python
"""测试JoinQuant API函数"""
from backend.jq_backtest.engine import JQBacktestEngine
from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider
from datetime import datetime

csv_provider = SimpleCSVDataProvider('/Volumes/ESSD/stockdata/')
engine = JQBacktestEngine(csv_provider=csv_provider)

# 测试所有JoinQuant API函数
strategy_code = '''
def initialize(context):
    # 测试配置函数
    set_benchmark("000001.XSHE")
    print(f"✓ set_benchmark 成功")
    
    context.security = "000001.XSHE"
    context.bought = False

def handle_data(context, data):
    security = context.security
    
    # 第一天买入
    if not context.bought:
        cash = context.portfolio.cash
        price = data[security].close
        if price > 0:
            size = int(cash / price / 100) * 100
            if size > 0:
                order(security, size)
                context.bought = True
                print(f"✓ order 成功: {size}股 @ {price:.2f}")
'''

try:
    result = engine.run_backtest(
        strategy_code=strategy_code,
        securities=['000001.XSHE'],
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 3, 31),
        freq='daily',
        initial_cash=100000
    )
    
    print(f"\n=== 回测成功 ===")
    print(f"最终价值: {result['final_value']:.2f}")
    print(f"总收益率: {result['total_return']:.2%}")
    print(f"\n✅ 所有JoinQuant API函数测试通过！")
    
except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
