#!/usr/bin/env python
"""测试回测引擎"""
from backend.jq_backtest.engine import JQBacktestEngine
from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider
from datetime import datetime

csv_provider = SimpleCSVDataProvider('/Volumes/ESSD/stockdata/')
engine = JQBacktestEngine(csv_provider=csv_provider)

strategy_code = '''
def initialize(context):
    context.security = "000001.XSHE"
    context.bought = False
    print(f"初始化策略，标的: {context.security}")

def handle_data(context, data):
    security = context.security
    print(f"Data keys: {[k for k in data._securities.keys()]}")
    print(f"handle_data called: bought={context.bought}, security={security}")
    
    # 第一天买入全部
    if not context.bought:
        cash = context.portfolio.cash
        price = data[security].close
        print(f"Cash={cash}, Price={price}")
        if price > 0:
            size = int(cash / price / 100) * 100  # 买入整手
            print(f"Calculated size={size}")
            if size > 0:
                result = order(security, size)
                print(f"Order result: {result}")
                context.bought = True
                print(f"买入 {security}: {size}股 @ {price:.2f}")
'''

result = engine.run_backtest(
    strategy_code=strategy_code,
    securities=['000001.XSHE'],
    start_date=datetime(2024, 1, 1),
    end_date=datetime(2024, 3, 31),
    freq='daily',
    initial_cash=100000
)

print(f"\n=== 回测完成 ===")
print(f"最终价值: {result['final_value']:.2f}")
print(f"总收益率: {result['total_return']:.2%}")
print(f"年化收益率: {result['annualized_return']:.2%}")
print(f"最大回撤: {result['max_drawdown']:.2%}")
print(f"夏普比率: {result['sharpe_ratio']:.2f}")
print(f"交易次数: {result['total_trades']}")
print(f"胜率: {result['win_rate']:.2%}")
