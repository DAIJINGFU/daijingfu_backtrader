"""
JoinQuant-compatible backtest engine based on backtrader

This is the main engine that orchestrates the backtest execution
"""
import re
import pandas as pd
import backtrader as bt
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from loguru import logger
import numpy as np

from backend.jq_backtest.context import Context, OrderCost, RunParams, g, reset_global_state
from backend.jq_backtest.portfolio import Portfolio
from backend.jq_backtest.strategy import JQStrategy
from backend.jq_backtest.csv_adapter import CSVDataFeedAdapter
from backend.jq_backtest.utils import (
    deduplicate_and_normalize,
    extract_security_candidates,
    normalize_security_code,
)
# 使用 SimpleCSVDataProvider 而不是 qlib 的 CSVDataProvider
from backend.data_provider import SimpleCSVDataProvider


class JQBacktestEngine:
    """
    Main backtest engine that runs JoinQuant-style strategies using backtrader
    """
    
    def __init__(self, csv_provider: Optional[SimpleCSVDataProvider] = None):
        self.cerebro: Optional[bt.Cerebro] = None
        self.results = None
        self.csv_provider = csv_provider
        self.csv_adapter = CSVDataFeedAdapter(csv_provider) if csv_provider else None
    
    def run_backtest(
        self,
        strategy_code: str,
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 1000000,
        securities: Optional[List[str]] = None,
        data_feeds: Optional[List[Tuple[str, pd.DataFrame]]] = None,
        commission: Optional[float] = None,
        stamp_duty: Optional[float] = None,
        min_commission: Optional[float] = None,
        freq: str = 'daily',
        fq: str = 'pre',
    ) -> Dict[str, Any]:
        """
        Run a backtest with JoinQuant-style strategy code
        
        Args:
            strategy_code: Python code containing initialize and handle_data functions
            start_date: Backtest start date
            end_date: Backtest end date
            initial_cash: Initial cash
            securities: Optional list of security codes to load from CSV provider
            data_feeds: List of (security_code, dataframe) tuples with OHLCV data (alternative to securities)
            commission: Optional commission rate override (falls back to strategy configuration)
            stamp_duty: Optional stamp duty rate override
            min_commission: Optional minimum commission override
            freq: Data frequency ('daily', 'minute')
            fq: Adjustment type ('pre', 'post', 'none')
        
        Returns:
            Dict with backtest results
        """
        logger.info(f"Starting backtest from {start_date} to {end_date}")

        run_params = RunParams(
            start_date=start_date,
            end_date=end_date,
            frequency=freq,
            initial_cash=initial_cash,
        )

        provided_codes = deduplicate_and_normalize(securities or []) if securities else []

        # First pass: bootstrap strategy to infer securities and cost settings
        reset_global_state()
        user_initialize, user_handle_data, before_trading, after_trading = self._parse_strategy_code(strategy_code)

        bootstrap_state = self._bootstrap_strategy(
            user_initialize=user_initialize,
            run_params=run_params,
        )

        inferred_universe = deduplicate_and_normalize(bootstrap_state.get('universe', []))
        extracted_from_globals = deduplicate_and_normalize(
            extract_security_candidates(bootstrap_state.get('global_values', []))
        )
        extracted_from_source = deduplicate_and_normalize(self._extract_codes_from_source(strategy_code))

        candidate_codes: List[str] = []
        candidate_codes.extend(provided_codes)
        candidate_codes.extend(inferred_universe)
        candidate_codes.extend(extracted_from_globals)
        candidate_codes.extend(extracted_from_source)

        target_securities = deduplicate_and_normalize(candidate_codes)

        if not target_securities and not data_feeds:
            raise ValueError(
                "未能从策略中推断出股票代码，请在 initialize 中设置 context.universe 或 g.security。"
            )

        cost_config = bootstrap_state.get('order_cost', OrderCost())
        commission_rate = commission if commission is not None else cost_config.open_commission
        stamp_duty_rate = stamp_duty if stamp_duty is not None else cost_config.stamp_duty
        min_commission_value = min_commission if min_commission is not None else cost_config.min_commission
        benchmark_code = bootstrap_state.get('benchmark')
        normalized_benchmark = (
            normalize_security_code(benchmark_code)
            if benchmark_code else None
        )

        # Note: benchmark is separate from trading securities, don't filter it out
        # Benchmark data will be loaded separately if needed for comparison

        # Reset and re-parse to ensure a clean environment for the real run
        reset_global_state()
        user_initialize, user_handle_data, before_trading, after_trading = self._parse_strategy_code(strategy_code)

        # Create cerebro instance
        self.cerebro = bt.Cerebro()

        # Set initial cash
        self.cerebro.broker.set_cash(initial_cash)

        # Set commission using inferred configuration
        self.cerebro.broker.setcommission(
            commission=commission_rate,
            stocklike=True,
            percabs=False,
        )

        loaded_securities: List[str] = list(target_securities)

        coverage_records: List[Dict[str, Any]] = []
        actual_start_candidates: List[datetime] = []
        actual_end_candidates: List[datetime] = []
        total_rows_loaded = 0

        # Add data feeds
        if target_securities and self.csv_adapter:
            logger.info(f"Loading data for {len(target_securities)} securities from CSV provider")
            feeds = self.csv_adapter.get_multiple_feeds(
                securities=target_securities,
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                fq=fq,
            )
            for security_code, data_feed in feeds:
                self.cerebro.adddata(data_feed, name=security_code)
                # Get bar count from metadata (feed is not loaded yet)
                bar_count = getattr(data_feed, '_qlib_rows', 'unknown')
                logger.info(f"Added data feed for {security_code}: {bar_count} bars")
                coverage_records.append({
                    'instrument': security_code,
                    'requested_start': start_date.isoformat(),
                    'requested_end': end_date.isoformat(),
                    'actual_start': getattr(data_feed, '_qlib_start', None).isoformat() if getattr(data_feed, '_qlib_start', None) else None,
                    'actual_end': getattr(data_feed, '_qlib_end', None).isoformat() if getattr(data_feed, '_qlib_end', None) else None,
                    'bars': getattr(data_feed, '_qlib_rows', bar_count if isinstance(bar_count, int) else None),
                })
                if getattr(data_feed, '_qlib_start', None):
                    actual_start_candidates.append(getattr(data_feed, '_qlib_start'))
                if getattr(data_feed, '_qlib_end', None):
                    actual_end_candidates.append(getattr(data_feed, '_qlib_end'))
                rows_loaded = getattr(data_feed, '_qlib_rows', None)
                if isinstance(rows_loaded, int):
                    total_rows_loaded += rows_loaded
                elif isinstance(bar_count, int):
                    total_rows_loaded += bar_count

        elif data_feeds:
            loaded_securities = []
            for security_code, df in data_feeds:
                data_feed = self._create_data_feed(df, start_date, end_date)
                data_feed._name = security_code  # Attach security code
                self.cerebro.adddata(data_feed, name=security_code)
                loaded_securities.append(security_code)
                logger.info(f"Added data feed for {security_code}: {len(df)} bars")
                coverage_records.append({
                    'instrument': security_code,
                    'requested_start': start_date.isoformat(),
                    'requested_end': end_date.isoformat(),
                    'actual_start': getattr(data_feed, '_qlib_start', None).isoformat() if getattr(data_feed, '_qlib_start', None) else None,
                    'actual_end': getattr(data_feed, '_qlib_end', None).isoformat() if getattr(data_feed, '_qlib_end', None) else None,
                    'bars': getattr(data_feed, '_qlib_rows', len(df)),
                })
                if getattr(data_feed, '_qlib_start', None):
                    actual_start_candidates.append(getattr(data_feed, '_qlib_start'))
                if getattr(data_feed, '_qlib_end', None):
                    actual_end_candidates.append(getattr(data_feed, '_qlib_end'))
                total_rows_loaded += len(df)
        else:
            raise ValueError("未能加载任何数据源，请检查数据提供者配置。")

        if not coverage_records:
            raise ValueError("请求的回测区间内未能加载到任何有效行情数据，请确认日期范围和数据源配置。")
        
        # Add strategy with CSV adapter reference
        self.cerebro.addstrategy(
            JQStrategy,
            user_initialize=user_initialize,
            user_handle_data=user_handle_data,
            before_trading_start=before_trading,
            after_trading_end=after_trading,
            run_params=run_params,
            csv_adapter=self.csv_adapter,  # Pass adapter for data API
        )
        
        # Add analyzers
        self.cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='sharpe')
        self.cerebro.addanalyzer(bt.analyzers.DrawDown, _name='drawdown')
        self.cerebro.addanalyzer(bt.analyzers.Returns, _name='returns')
        self.cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name='trades')
        
        # Run backtest
        logger.info("Running backtest...")
        import time
        start_time = time.time()
        
        self.results = self.cerebro.run()
        
        elapsed_time = time.time() - start_time
        logger.info(f"Backtest execution took {elapsed_time:.2f} seconds")
        
        # Extract results
        final_value = self.cerebro.broker.getvalue()
        total_return = (final_value - initial_cash) / initial_cash
        
        strategy_results = self.results[0]
        
        # Get tracked time series data
        equity_curve = strategy_results.equity_curve
        daily_returns = strategy_results.daily_returns
        position_history = strategy_results.position_history
        trade_list = strategy_results.trade_list
        drawdown_curve = strategy_results.drawdown_curve

        if equity_curve:
            try:
                equity_start = datetime.fromisoformat(equity_curve[0]['datetime'])
                equity_end = datetime.fromisoformat(equity_curve[-1]['datetime'])
                actual_start_candidates.append(equity_start)
                actual_end_candidates.append(equity_end)
            except Exception:
                logger.debug("Failed to parse equity curve datetimes for coverage summary")
        
        actual_start_date = min(actual_start_candidates) if actual_start_candidates else None
        actual_end_date = max(actual_end_candidates) if actual_end_candidates else None

        # Calculate additional metrics
        periods_per_year = 252 if freq == 'daily' else 252 * 240
        risk_free_rate = 0.0  # TODO: make configurable when needed

        returns_array = (
            np.array([r['value'] for r in daily_returns], dtype=float)
            if daily_returns else np.array([], dtype=float)
        )

        mean_return = float(np.mean(returns_array)) if returns_array.size > 0 else 0.0
        per_period_volatility = (
            float(np.std(returns_array, ddof=1))
            if returns_array.size > 1 else 0.0
        )
        annualized_volatility = (
            per_period_volatility * np.sqrt(periods_per_year)
            if per_period_volatility > 0 else 0.0
        )

        sharpe_ratio = 0.0
        if per_period_volatility > 0:
            excess_mean = mean_return - (risk_free_rate / periods_per_year)
            sharpe_ratio = excess_mean / per_period_volatility * np.sqrt(periods_per_year)

        total_days = max((end_date - start_date).days, 0)
        annualized_return = 0.0
        if total_days > 0 and final_value > 0 and initial_cash > 0:
            years = total_days / 365.25
            if years > 0:
                annualized_return = (final_value / initial_cash) ** (1 / years) - 1
        elif total_days == 0:
            annualized_return = total_return
        else:
            annualized_return = 0.0

        # Calculate trade analytics
        total_trades = strategy_results.winning_trades + strategy_results.losing_trades
        win_rate = strategy_results.winning_trades / total_trades if total_trades > 0 else 0.0
        profit_factor = strategy_results.total_profit / strategy_results.total_loss if strategy_results.total_loss > 0 else 0.0
        
        # Calculate Sortino and Calmar ratios
        sortino_ratio = 0.0
        if returns_array.size > 0:
            downside_returns = returns_array[returns_array < 0]
            if downside_returns.size > 0:
                downside_std = (
                    float(np.std(downside_returns, ddof=1))
                    if downside_returns.size > 1
                    else float(np.std(downside_returns))
                )
                if downside_std > 0:
                    excess_mean = mean_return - (risk_free_rate / periods_per_year)
                    sortino_ratio = excess_mean / downside_std * np.sqrt(periods_per_year)

        max_drawdown_percent = strategy_results.analyzers.drawdown.get_analysis().get('max', {}).get('drawdown', 0)
        max_drawdown_decimal = (max_drawdown_percent / 100) if max_drawdown_percent else 0.0
        calmar_ratio = 0.0
        if max_drawdown_decimal > 0:
            calmar_ratio = annualized_return / max_drawdown_decimal
        
        # Calculate rolling Sharpe ratio (30-day window)
        rolling_sharpe = []
        window_size = 30
        if returns_array.size >= window_size:
            for i in range(window_size - 1, returns_array.size):
                window_returns = returns_array[i - window_size + 1:i + 1]
                window_std = (
                    float(np.std(window_returns, ddof=1))
                    if window_returns.size > 1 else 0.0
                )
                if window_std > 0:
                    window_mean = float(np.mean(window_returns))
                    excess_window_mean = window_mean - (risk_free_rate / periods_per_year)
                    sharpe = excess_window_mean / window_std * np.sqrt(periods_per_year)
                else:
                    sharpe = 0.0
                rolling_sharpe.append({
                    'datetime': daily_returns[i]['datetime'],
                    'value': sharpe
                })
        
        # Generate unique backtest ID
        import uuid
        backtest_id = str(uuid.uuid4())[:8]
        
        # Transform position history to flat format expected by frontend
        # From: [{datetime, positions: {security: {size, price}}}]
        # To: [{datetime, instrument, amount, price, value, weight}]
        flat_positions = []
        for pos_record in position_history:
            dt = pos_record['datetime']
            positions = pos_record['positions']
            
            # Calculate total portfolio value for this datetime
            total_value = sum(p['size'] * p['price'] for p in positions.values())
            
            for security, pos_data in positions.items():
                amount = pos_data['size']
                price = pos_data['price']
                value = amount * price
                weight = value / total_value if total_value > 0 else 0
                
                flat_positions.append({
                    'datetime': dt,
                    'instrument': security,
                    'amount': amount,
                    'price': price,
                    'value': value,
                    'weight': weight,
                })
        
        result_dict = {
            'backtest_id': backtest_id,
            'status': 'completed',
            'initial_cash': initial_cash,
            'final_value': final_value,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annualized_volatility': annualized_volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown_percent,
            'sortino_ratio': sortino_ratio,
            'calmar_ratio': calmar_ratio,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'total_trades': total_trades,
            'winning_trades': strategy_results.winning_trades,
            'losing_trades': strategy_results.losing_trades,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'actual_start_date': actual_start_date.isoformat() if actual_start_date else None,
            'actual_end_date': actual_end_date.isoformat() if actual_end_date else None,
            'securities': loaded_securities,
            'commission': commission_rate,
            'stamp_duty': stamp_duty_rate,
            'min_commission': min_commission_value,
            'equity_curve': equity_curve,
            'daily_returns': daily_returns,
            'drawdown_curve': drawdown_curve,
            'rolling_sharpe': rolling_sharpe,
            'positions': flat_positions,
            'trades': trade_list,
            'data_coverage': coverage_records,
            'bars_loaded': total_rows_loaded,
        }

        # Load and calculate benchmark if specified
        if benchmark_code and self.csv_adapter:
            result_dict['benchmark'] = benchmark_code
            benchmark_data = self._load_benchmark_data(
                normalized_benchmark, start_date, end_date, freq, fq
            )
            if benchmark_data:
                result_dict.update(benchmark_data)
        
        logger.info(f"Backtest completed. Final value: {final_value:.2f}, Return: {total_return*100:.2f}%")
        
        return result_dict
    
    def _bootstrap_strategy(
        self,
        *,
        user_initialize: Optional[Callable],
        run_params: RunParams,
    ) -> Dict[str, Any]:
        """Execute strategy initialization in isolation to infer configuration."""

        bootstrap_context = Context(run_params)
        bootstrap_context.portfolio = Portfolio(
            starting_cash=run_params.initial_cash if hasattr(run_params, 'initial_cash') else 1000000
        )

        scheduled_records: List[Tuple[str, str, str]] = []

        def record_schedule(kind: str, func: Callable, time_str: str) -> Callable:
            scheduled_records.append((kind, getattr(func, '__name__', '<anonymous>'), time_str))
            return func

        def run_daily(func: Callable, time: str = '9:30', reference_security: Optional[str] = None) -> Callable:
            return record_schedule('daily', func, time)

        def run_weekly(
            func: Callable,
            weekday: int,
            time: str = '9:30',
            reference_security: Optional[str] = None,
        ) -> Callable:
            return record_schedule(f'weekly[{weekday}]', func, time)

        def run_monthly(
            func: Callable,
            monthday: int,
            time: str = '9:30',
            reference_security: Optional[str] = None,
        ) -> Callable:
            return record_schedule(f'monthly[{monthday}]', func, time)

        def set_benchmark(value: str) -> None:
            bootstrap_context.benchmark = value

        def set_order_cost(cost: Union[OrderCost, Dict[str, Any]], type: str = 'stock', security_type: str = None) -> OrderCost:
            # Accept both 'type' (JoinQuant style) and 'security_type' parameters
            if security_type is None:
                security_type = type
                
            if isinstance(cost, dict):
                cost_obj = OrderCost(**cost)
            elif isinstance(cost, OrderCost):
                cost_obj = cost
            else:
                raise TypeError("set_order_cost expects OrderCost or dict")

            bootstrap_context.order_cost = cost_obj
            bootstrap_context.commission_rate = cost_obj.open_commission
            bootstrap_context.stamp_duty_rate = cost_obj.stamp_duty
            return cost_obj

        def make_noop(name: str) -> Callable:
            def _noop(*args: Any, **kwargs: Any) -> None:
                logger.debug("Bootstrap stub '%s' invoked; ignoring.", name)
                return None

            return _noop

        def make_data_stub(name: str) -> Callable:
            def _stub(*args: Any, **kwargs: Any) -> pd.DataFrame:
                logger.debug("Bootstrap stub '%s' invoked; returning empty DataFrame.", name)
                return pd.DataFrame()

            return _stub

        bootstrap_bindings: Dict[str, Any] = {
            'context': bootstrap_context,
            'g': g,
            'set_option': bootstrap_context.set_option,
            'set_benchmark': set_benchmark,
            'set_order_cost': set_order_cost,
            'run_daily': run_daily,
            'run_weekly': run_weekly,
            'run_monthly': run_monthly,
            'order': make_noop('order'),
            'order_target': make_noop('order_target'),
            'order_value': make_noop('order_value'),
            'order_target_value': make_noop('order_target_value'),
            'history': make_data_stub('history'),
            'attribute_history': make_data_stub('attribute_history'),
            'get_price': make_data_stub('get_price'),
            'get_fundamentals': make_data_stub('get_fundamentals'),
        }

        if user_initialize:
            target_globals = user_initialize.__globals__
            target_globals.update(bootstrap_bindings)
            try:
                user_initialize(bootstrap_context)
            except Exception as exc:
                logger.warning(f"Bootstrap initialize failed: {exc}", exc_info=True)

        global_values = [value for _, value in g.items()]

        return {
            'universe': list(bootstrap_context.universe),
            'global_values': global_values,
            'order_cost': bootstrap_context.order_cost,
            'benchmark': bootstrap_context.benchmark,
            'scheduled': scheduled_records,
        }

    def _extract_codes_from_source(self, source: str) -> List[str]:
        """Return security-like codes defined literally inside the strategy source."""
        if not source:
            return []

        matches = re.findall(r"['\"](\d{6}(?:\.(?:XSHE|XSHG|SZ|SH))?)['\"]", source)
        return matches

    def _create_data_feed(
        self,
        df: pd.DataFrame,
        start_date: datetime,
        end_date: datetime,
    ) -> bt.feeds.PandasData:
        """
        Create a backtrader data feed from a pandas DataFrame
        
        Args:
            df: DataFrame with OHLCV data (datetime index)
            start_date: Start date for filtering
            end_date: End date for filtering
        
        Returns:
            Backtrader PandasData feed
        """
        # Ensure datetime index
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'date' in df.columns:
                df = df.set_index('date')
                df.index = pd.to_datetime(df.index)
            elif 'datetime' in df.columns:
                df = df.set_index('datetime')
                df.index = pd.to_datetime(df.index)
        
        # Filter by date range
        df = df[(df.index >= start_date) & (df.index <= end_date)]

        # Ensure required columns exist
        required_cols = ['open', 'high', 'low', 'close', 'volume']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")

        if df.empty:
            raise ValueError(
                f"No data available between {start_date} and {end_date}"
            )
        actual_start = df.index.min()
        actual_end = df.index.max()
        if actual_start > start_date:
            logger.info(
                "Adjusted custom feed start from %s to %s",
                start_date,
                actual_start,
            )
        if actual_end < end_date:
            logger.info(
                "Adjusted custom feed end from %s to %s",
                end_date,
                actual_end,
            )
        
        # Create data feed
        data_feed = bt.feeds.PandasData(
            dataname=df,
            datetime=None,  # Use index
            open='open',
            high='high',
            low='low',
            close='close',
            volume='volume',
            openinterest=-1,  # Not used
        )

        data_feed._qlib_requested_start = start_date
        data_feed._qlib_requested_end = end_date
        data_feed._qlib_start = actual_start
        data_feed._qlib_end = actual_end
        data_feed._qlib_rows = len(df)
        
        return data_feed
    
    def _parse_strategy_code(self, strategy_code: str) -> Tuple[
        Optional[Callable],
        Optional[Callable],
        Optional[Callable],
        Optional[Callable],
    ]:
        """
        Parse strategy code and extract functions
        
        Args:
            strategy_code: Python code as string
        
        Returns:
            Tuple of (initialize, handle_data, before_trading_start, after_trading_end)
        """
        # Create execution namespace with trading API functions
        from backend.jq_backtest import (
            order, order_target, order_value, order_target_value, log, g,
            set_benchmark, set_option, set_commission, set_slippage, set_order_cost,
            run_daily, run_weekly, run_monthly, OrderCost
        )
        
        namespace = {
            # Trading functions
            'order': order,
            'order_target': order_target,
            'order_value': order_value,
            'order_target_value': order_target_value,
            'log': log,
            'g': g,
            # Configuration functions
            'set_benchmark': set_benchmark,
            'set_option': set_option,
            'set_commission': set_commission,
            'set_slippage': set_slippage,
            'set_order_cost': set_order_cost,
            # Scheduling functions
            'run_daily': run_daily,
            'run_weekly': run_weekly,
            'run_monthly': run_monthly,
            # Classes
            'OrderCost': OrderCost,
        }
        
        # Execute code to define functions
        try:
            exec(strategy_code, namespace)
        except Exception as e:
            logger.error(f"Error parsing strategy code: {e}")
            raise
        
        # Extract functions
        initialize = namespace.get('initialize')
        handle_data = namespace.get('handle_data')
        before_trading_start = namespace.get('before_trading_start')
        after_trading_end = namespace.get('after_trading_end')
        
        return initialize, handle_data, before_trading_start, after_trading_end
    
    def _load_benchmark_data(
        self,
        benchmark_code: str,
        start_date: datetime,
        end_date: datetime,
        freq: str = 'daily',
        fq: str = 'pre',
    ) -> Dict[str, Any]:
        """
        Load benchmark data and calculate benchmark metrics
        
        Args:
            benchmark_code: Benchmark security code
            start_date: Start date
            end_date: End date
            freq: Data frequency
            fq: Adjustment type
        
        Returns:
            Dict with benchmark metrics
        """
        try:
            logger.info(f"Loading benchmark data for {benchmark_code}")
            
            # Load benchmark data
            feeds = self.csv_adapter.get_multiple_feeds(
                securities=[benchmark_code],
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                fq=fq,
            )
            
            if not feeds:
                logger.warning(f"No benchmark data found for {benchmark_code}")
                return {}
            
            # Get the benchmark feed
            _, benchmark_feed = feeds[0]
            
            # Extract close prices
            benchmark_curve = []
            benchmark_returns = []
            prev_close = None
            
            # Use a minimal cerebro to iterate through the benchmark data
            temp_cerebro = bt.Cerebro()
            temp_cerebro.adddata(benchmark_feed, name=benchmark_code)
            
            # Simple strategy to extract data
            class BenchmarkExtractor(bt.Strategy):
                def __init__(self):
                    self.curve = []
                    self.returns = []
                    self.prev_close = None
                
                def next(self):
                    dt = self.datas[0].datetime.datetime(0)
                    close = self.datas[0].close[0]
                    
                    # Track curve (normalized to initial value of 1.0)
                    if not self.curve:
                        self.curve.append({
                            'datetime': dt.isoformat(),
                            'value': 1.0
                        })
                        self.prev_close = close
                    else:
                        normalized_value = close / self.prev_close if self.prev_close else 1.0
                        self.curve.append({
                            'datetime': dt.isoformat(),
                            'value': normalized_value * self.curve[-1]['value']
                        })
                    
                    # Track returns
                    if self.prev_close is not None:
                        ret = (close - self.prev_close) / self.prev_close
                        self.returns.append({
                            'datetime': dt.isoformat(),
                            'value': ret
                        })
                    
                    self.prev_close = close
            
            temp_cerebro.addstrategy(BenchmarkExtractor)
            results = temp_cerebro.run()
            extractor = results[0]
            
            benchmark_curve = extractor.curve
            benchmark_returns = extractor.returns
            
            # Calculate benchmark metrics
            if benchmark_returns:
                returns_values = [r['value'] for r in benchmark_returns]
                import numpy as np
                
                total_return_benchmark = (benchmark_curve[-1]['value'] - 1.0) if benchmark_curve else 0.0
                mean_return = np.mean(returns_values) if returns_values else 0.0
                std_return = np.std(returns_values) if returns_values else 0.0
                
                # Annualize
                trading_days = len(returns_values)
                if trading_days > 0:
                    annualized_return_benchmark = mean_return * 252
                    annualized_volatility_benchmark = std_return * np.sqrt(252)
                    sharpe_benchmark = annualized_return_benchmark / annualized_volatility_benchmark if annualized_volatility_benchmark > 0 else 0.0
                else:
                    annualized_return_benchmark = 0.0
                    annualized_volatility_benchmark = 0.0
                    sharpe_benchmark = 0.0
                
                # Max drawdown
                max_dd = 0.0
                peak = benchmark_curve[0]['value'] if benchmark_curve else 1.0
                for point in benchmark_curve:
                    if point['value'] > peak:
                        peak = point['value']
                    dd = (peak - point['value']) / peak if peak > 0 else 0.0
                    if dd > max_dd:
                        max_dd = dd
                
                return {
                    'benchmark_curve': benchmark_curve,
                    'benchmark_returns': benchmark_returns,
                    'benchmark_total_return': total_return_benchmark,
                    'benchmark_annualized_return': annualized_return_benchmark,
                    'benchmark_sharpe': sharpe_benchmark,
                    'benchmark_max_drawdown': max_dd,
                }
            
            return {}
        
        except Exception as e:
            logger.error(f"Error loading benchmark data: {e}")
            return {}
    
    def plot(self):
        """Plot backtest results"""
        if self.cerebro:
            self.cerebro.plot()
