"""
回测服务接口定义
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any


class IBacktestService(ABC):
    """回测服务接口"""
    
    @abstractmethod
    def run_backtest(
        self,
        strategy_code: str,
        start_date: datetime,
        end_date: datetime,
        initial_cash: float = 1000000,
        securities: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """运行回测"""
        pass
