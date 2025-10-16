"""测试订单执行的调试脚本"""
import os
os.environ['DATA_ROOT'] = '/Volumes/ESSD/stockdata/'

from datetime import datetime
from backend.jq_backtest.engine import JQBacktestEngine
from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider

# 初始化
data_provider = SimpleCSVDataProvider('/Volumes/ESSD/stockdata/')
engine = JQBacktestEngine(csv_provider=data_provider)

# 策略代码（与前端默认策略一致）
strategy_code = """
def initialize(context):
    set_benchmark('000300.XSHG')
    set_option('use_real_price', True)
    set_order_cost(OrderCost(
        open_commission=0.0003,
        close_commission=0.0003,
        close_tax=0.001,
        min_commission=5
    ))
    g.security = '000001.XSHE'
    context.universe = [g.security]
    print("策略初始化完成")

def handle_data(context, data):
    security = g.security
    current_price = data[security].close
    position = context.portfolio.positions.get(security)
    current_amount = position.total_amount if position else 0
    
    if current_price > 10 and current_amount == 0:
        cash = context.portfolio.available_cash
        print(f"[STRATEGY] 价格 {current_price:.2f} > 10, 现金 {cash:.2f}, 尝试买入 80%")
        if cash > 10000:
            order_value(security, cash * 0.8)
            print(f"{context.current_dt.date()}: 买入 {security}")
    elif current_price < 10 and current_amount > 0:
        order_target(security, 0)
        print(f"{context.current_dt.date()}: 卖出 {security}")
"""

# 运行回测（缩短时间以便快速测试）
result = engine.run_backtest(
    strategy_code=strategy_code,
    start_date=datetime(2023, 1, 1),
    end_date=datetime(2023, 1, 31),  # 只测试1月
    initial_cash=1000000,
    securities=['000001.XSHE'],
    freq='daily',
    fq='pre'
)

print(f"\n=== 测试结果 ===")
print(f"回测ID: {result.get('backtest_id', 'N/A')}")
print(f"状态: {result.get('status', 'N/A')}")
print(f"初始资金: {result['initial_cash']:.2f}")
print(f"最终价值: {result['final_value']:.2f}")
print(f"收益率: {result['total_return']*100:.2f}%")
print(f"交易次数: {result.get('total_trades', 0)}")
