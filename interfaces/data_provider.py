"""
数据提供者接口定义
与主系统 CSVDataProvider 兼容
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
import pandas as pd


class IDataProvider(ABC):
    """数据提供者接口"""
    
    @abstractmethod
    def load_data(
        self,
        security: str,
        start_date: datetime,
        end_date: datetime,
        freq: str = 'daily',
        adjust: str = 'pre'
    ) -> pd.DataFrame:
        """
        加载单个证券的历史数据
        
        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume
        """
        pass
    
    @abstractmethod
    def get_price(
        self,
        security: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = 'daily',
        fields: Optional[List[str]] = None,
        fq: str = 'pre'
    ) -> pd.DataFrame:
        """获取价格数据"""
        pass
