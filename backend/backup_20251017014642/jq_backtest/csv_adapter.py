"""
CSV数据适配器
"""
from datetime import datetime
from typing import List, Tuple, Dict, Any
import pandas as pd
import backtrader as bt
from loguru import logger


class CSVDataFeedAdapter:
    """CSV数据适配器"""
    
    def __init__(self, data_provider):
        self.data_provider = data_provider
    
    def load_data(
        self,
        security: str,
        start_date: datetime,
        end_date: datetime,
        freq: str = 'daily',
        fq: str = 'pre'
    ) -> pd.DataFrame:
        """加载数据"""
        logger.info(f"Loading data for {security} from {start_date} to {end_date}")
        
        # 转换fq到adjust参数
        # fq: 'pre' (前复权), 'post' (后复权), 'none' (不复权)
        adjust_map = {
            'pre': 'pre',
            'post': 'post',
            'none': 'none',
            'qfq': 'pre',  # 聚宽术语
            'hfq': 'post',  # 聚宽术语
        }
        adjust = adjust_map.get(fq, 'none')
        
        # 首先尝试使用指定的复权类型
        df = self.data_provider.load_data(
            security=security,
            start_date=start_date,
            end_date=end_date,
            freq=freq,
            adjust=adjust
        )
        
        # 如果没有数据且不是'none'，回退到不复权数据
        if df.empty and adjust != 'none':
            logger.warning(f"No {adjust} adjusted data for {security}, trying unadjusted data")
            df = self.data_provider.load_data(
                security=security,
                start_date=start_date,
                end_date=end_date,
                freq=freq,
                adjust='none'
            )
        
        if df.empty:
            logger.warning(f"No data found for {security}")
        else:
            logger.info(f"Loaded {len(df)} rows for {security}")
        
        return df
    
    def get_multiple_feeds(
        self,
        securities: List[str],
        start_date: datetime,
        end_date: datetime,
        freq: str = 'daily',
        fq: str = 'pre'
    ) -> List[Tuple[str, bt.feeds.PandasData]]:
        """
        加载多个证券的数据并转换为backtrader数据feed
        
        Args:
            securities: 证券代码列表
            start_date: 开始日期
            end_date: 结束日期
            freq: 频率
            fq: 复权类型
            
        Returns:
            List of (security_code, bt_datafeed) tuples
        """
        feeds = []
        
        for security in securities:
            df = self.load_data(security, start_date, end_date, freq, fq)
            
            if not df.empty:
                # 调试：打印DataFrame信息
                logger.debug(f"DataFrame for {security}:")
                logger.debug(f"  Columns: {df.columns.tolist()}")
                logger.debug(f"  Index: {df.index.name}")
                logger.debug(f"  First row:\n{df.head(1)}")
                
                # 转换为backtrader数据feed
                bt_feed = bt.feeds.PandasData(
                    dataname=df,
                    datetime=None,  # 使用索引作为日期
                    open='open',
                    high='high',
                    low='low',
                    close='close',
                    volume='volume',
                    openinterest=-1  # 股票没有持仓量
                )
                
                # 添加元数据属性
                bt_feed._name = security
                bt_feed._qlib_start = df.index[0]
                bt_feed._qlib_end = df.index[-1]
                bt_feed._qlib_rows = len(df)
                
                feeds.append((security, bt_feed))
                logger.info(f"Created backtrader feed for {security}: {len(df)} bars")
            else:
                logger.warning(f"Skipping {security} - no data available")
        
        return feeds
