"""测试持仓数据格式"""
import os
os.environ['DATA_ROOT'] = '/Volumes/ESSD/stockdata/'

from datetime import datetime
from backend.jq_backtest.engine import JQBacktestEngine
from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider
import json

# 初始化
data_provider = SimpleCSVDataProvider('/Volumes/ESSD/stockdata/')
engine = JQBacktestEngine(csv_provider=data_provider)

# 策略代码
strategy_code = """
def initialize(context):
    set_benchmark('000300.XSHG')
    g.security = '000001.XSHE'
    print("策略初始化完成")

def handle_data(context, data):
    security = g.security
    current_price = data[security].close
    position = context.portfolio.positions.get(security)
    current_amount = position.total_amount if position else 0
    
    if current_price > 10 and current_amount == 0:
        cash = context.portfolio.available_cash
        if cash > 10000:
            order_value(security, cash * 0.8)
"""

# 运行回测
result = engine.run_backtest(
    strategy_code=strategy_code,
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 1, 31),
    initial_cash=1000000,
    securities=['000001.XSHE'],
    freq='daily',
    fq='pre'
)

print(f"\n=== 持仓数据格式测试 ===")
print(f"持仓记录数: {len(result['positions'])}")
if result['positions']:
    print(f"\n第一条记录:")
    print(json.dumps(result['positions'][0], indent=2, ensure_ascii=False))
    print(f"\n最后一条记录:")
    print(json.dumps(result['positions'][-1], indent=2, ensure_ascii=False))
