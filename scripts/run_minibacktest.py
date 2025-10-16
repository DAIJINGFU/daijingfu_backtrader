from backend.jq_backtest.engine import JQBacktestEngine
from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider as SimpleCSVDataProvider
from datetime import datetime
import traceback

provider = SimpleCSVDataProvider(r'd:\JoinQuant\VScode\2025.917MY_LOCALSYSTEM_BACKTEST\starquant4-backtest\stockdata\stockdata')
engine = JQBacktestEngine(csv_provider=provider)

strategy_code = '''
def initialize(context):
    # use a single security
    context.universe = ['000001.XSHE']

def handle_data(context, data):
    pass
'''

try:
    res = engine.run_backtest(
        strategy_code=strategy_code,
        start_date=datetime(2020,1,2),
        end_date=datetime(2020,1,10),
        initial_cash=100000,
        securities=['000001.XSHE'],
        freq='daily',
        fq='pre'
    )
    print('Backtest returned:', res.get('backtest_id'))
except Exception as e:
    print('Exception during backtest:')
    traceback.print_exc()
