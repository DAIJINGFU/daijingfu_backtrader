"""
JoinQuant策略适配器
"""
import backtrader as bt
from typing import Optional
from loguru import logger
from backend.jq_backtest.context import Context, g
from backend.jq_backtest.trading_api import TradingAPI
from backend.jq_backtest.data_api import DataAPI, DataProxy, SecurityData


class JQStrategy(bt.Strategy):
    """Backtrader策略适配器"""
    
    params = (
        ('user_initialize', None),
        ('user_handle_data', None),
        ('before_trading_start', None),
        ('after_trading_start', None),
        ('after_trading_end', None),
        ('run_params', None),
        ('csv_adapter', None),
        ('context', None),
    )
    
    def __init__(self):
        logger.info("Initializing JQStrategy")
        self.context = self.params.context or Context()
        self.trading_api = TradingAPI(self)
        self.data_api = DataAPI(self)
        self._initialized = False
        self.csv_adapter = self.params.csv_adapter  # 保存csv_adapter引用
        self._last_date = None  # 追踪日期变化，用于before_trading_start
        
        # 初始化追踪数据
        self.equity_curve = []
        self.daily_returns = []
        self.position_history = []
        self.trade_list = []
        self.drawdown_curve = []
        
        # 交易统计
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
    
    def start(self):
        """策略启动时调用"""
        logger.info("Strategy starting...")
        
        # 初始化portfolio
        initial_cash = self.broker.getcash()
        from backend.jq_backtest.portfolio import Portfolio
        self.context.portfolio = Portfolio(starting_cash=initial_cash)
        
        # 调用用户的initialize函数
        if self.params.user_initialize and not self._initialized:
            try:
                # 设置当前策略上下文
                from backend.jq_backtest import _set_current_strategy, _clear_current_strategy
                _set_current_strategy(self)
                try:
                    self.params.user_initialize(self.context)
                    self._initialized = True
                    logger.info("User initialize completed")
                finally:
                    _clear_current_strategy()
            except Exception as e:
                logger.error(f"Error in initialize: {e}")
                raise
    
    def prenext(self):
        """在数据不足时调用（预热期）"""
        # 直接调用next逻辑
        self.next()
    
    def next(self):
        """每个数据点调用"""
        # 更新context的当前时间
        current_dt = self.datas[0].datetime.datetime(0)
        self.context.current_dt = current_dt
        current_date = current_dt.date()
        
        # 如果日期变化，调用before_trading_start
        if self._last_date != current_date:
            if self.params.before_trading_start:
                try:
                    self.params.before_trading_start(self.context, None)
                except Exception as e:
                    logger.error(f"Error in before_trading_start: {e}")
                    raise
            self._last_date = current_date
        
        # 构建data对象
        data = DataProxy()
        security_mapping = {}  # 映射：标准化代码 -> 原始代码
        
        for d in self.datas:
            security = d._name  # 标准化后的代码 (例如 '000001.SZ')
            close_val = d.close[0]
            open_val = d.open[0]
            
            # 调试：第一次打印详细信息
            if current_dt.day == 2 and len(data._securities) == 0:
                logger.debug(f"Data feed debug for {security}:")
                logger.debug(f"  close[0]={close_val}, open[0]={open_val}")
                logger.debug(f"  high[0]={d.high[0]}, low[0]={d.low[0]}")
            
            sec_data = SecurityData(security, {
                'close': close_val,
                'open': open_val,
                'high': d.high[0],
                'low': d.low[0],
                'volume': d.volume[0] if hasattr(d, 'volume') else 0,
            })
            
            # 同时使用标准化代码和可能的原始代码
            data[security] = sec_data
            security_mapping[security] = security
            
            # 如果是 XSHG/XSHE 格式，也添加 SH/SZ 格式的映射
            if '.XSHG' in security or '.XSHE' in security:
                alt_code = security.replace('.SZ', '.XSHE').replace('.SH', '.XSHG')
                if alt_code != security:
                    data[alt_code] = sec_data
                    security_mapping[alt_code] = security
            elif '.SZ' in security or '.SH' in security:
                # 反向：如果数据是 SZ/SH 格式，也支持 XSHE/XSHG 访问
                if '.SZ' in security:
                    alt_code = security.replace('.SZ', '.XSHE')
                elif '.SH' in security:
                    alt_code = security.replace('.SH', '.XSHG')
                data[alt_code] = sec_data
                security_mapping[alt_code] = security
        
        # 更新portfolio信息
        self.context.portfolio.available_cash = self.broker.getcash()
        for d in self.datas:
            security = d._name
            position = self.getposition(d)
            if position.size != 0:
                portfolio_pos = self.context.portfolio.get_position(security)
                portfolio_pos.total_amount = int(position.size)
                portfolio_pos.avg_cost = position.price
                portfolio_pos.update_price(d.close[0])
        self.context.portfolio.update_value()
        
        # 调用用户的handle_data
        if self.params.user_handle_data:
            try:
                # 设置当前策略上下文
                from backend.jq_backtest import _set_current_strategy, _clear_current_strategy
                _set_current_strategy(self)
                try:
                    self.params.user_handle_data(self.context, data)
                finally:
                    _clear_current_strategy()
            except Exception as e:
                logger.error(f"Error in handle_data: {e}")
                raise
        
        # 记录追踪数据
        portfolio_value = self.broker.getvalue()
        self.equity_curve.append({
            'datetime': current_dt.isoformat(),
            'portfolio_value': portfolio_value,
        })
        
        # 记录持仓
        positions_data = {}
        for d in self.datas:
            security = d._name
            position = self.getposition(d)
            if position.size != 0:
                positions_data[security] = {
                    'size': position.size,
                    'price': position.price,
                }
        
        if positions_data:
            self.position_history.append({
                'datetime': current_dt.isoformat(),
                'positions': positions_data,
            })
    
    def notify_trade(self, trade):
        """交易完成通知"""
        if trade.isclosed:
            pnl = trade.pnl
            if pnl > 0:
                self.winning_trades += 1
                self.total_profit += pnl
            elif pnl < 0:
                self.losing_trades += 1
                self.total_loss += abs(pnl)
            
            # 记录交易
            self.trade_list.append({
                'datetime': self.datas[0].datetime.datetime(0).isoformat(),
                'security': trade.data._name,
                'size': trade.size,
                'price': trade.price,
                'pnl': pnl,
            })
    
    def submit_order(self, order_obj):
        """Submit an order to the broker"""
        # 标准化证券代码
        security = order_obj.security
        # 尝试查找匹配的数据 feed
        target_data = None
        for d in self.datas:
            # 检查精确匹配或代码转换匹配
            if d._name == security:
                target_data = d
                break
            # 检查 XSHE<->SZ 和 XSHG<->SH 的转换
            if ('.XSHE' in security and '.SZ' in d._name) or ('.SZ' in security and '.XSHE' in d._name):
                if security.split('.')[0] == d._name.split('.')[0]:
                    target_data = d
                    break
            if ('.XSHG' in security and '.SH' in d._name) or ('.SH' in security and '.XSHG' in d._name):
                if security.split('.')[0] == d._name.split('.')[0]:
                    target_data = d
                    break
        
        if target_data is None:
            logger.warning(f"Security {security} not found in data feeds. Available: {[d._name for d in self.datas]}")
            return None
        
        # Submit order using backtrader's buy/sell methods
        if order_obj.amount > 0:
            # Buy order
            self.buy(data=target_data, size=order_obj.amount)
            logger.info(f"Submitted BUY order: {security} ({target_data._name}), size={order_obj.amount}")
        elif order_obj.amount < 0:
            # Sell order
            self.sell(data=target_data, size=abs(order_obj.amount))
            logger.info(f"Submitted SELL order: {security} ({target_data._name}), size={abs(order_obj.amount)}")
        
        return order_obj
    
    def get_current_price(self, security: str) -> Optional[float]:
        """Get current price for a security"""
        # 尝试精确匹配
        for d in self.datas:
            if d._name == security:
                return d.close[0]
        
        # 尝试代码转换匹配 (XSHE<->SZ, XSHG<->SH)
        for d in self.datas:
            # XSHE <-> SZ
            if ('.XSHE' in security and '.SZ' in d._name) or ('.SZ' in security and '.XSHE' in d._name):
                if security.split('.')[0] == d._name.split('.')[0]:
                    return d.close[0]
            # XSHG <-> SH
            if ('.XSHG' in security and '.SH' in d._name) or ('.SH' in security and '.XSHG' in d._name):
                if security.split('.')[0] == d._name.split('.')[0]:
                    return d.close[0]
        
        return None
    
    def stop(self):
        """策略结束时调用"""
        logger.info("Strategy stopping...")
        if self.params.after_trading_end:
            try:
                self.params.after_trading_end(self.context, None)
                logger.info("after_trading_end completed")
            except Exception as e:
                logger.error(f"Error in after_trading_end: {e}")
                raise
    
    def get_history_data(self, **kwargs):
        """获取历史数据 - 简化实现"""
        import pandas as pd
        return pd.DataFrame()
    
    def get_price_data(self, **kwargs):
        """获取价格数据 - 简化实现"""
        import pandas as pd
        return pd.DataFrame()
