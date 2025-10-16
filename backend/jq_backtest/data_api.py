"""
Data API functions for JoinQuant-compatible strategies
"""
from typing import Optional, Union, List
import pandas as pd
from datetime import datetime, timedelta


class SecurityData:
    """
    Data object for a single security at current bar
    """
    def __init__(self, security: str, data: dict):
        self.security = security
        self._data = data
        
        # Common fields
        self.close = data.get('close', 0.0)
        self.open = data.get('open', 0.0)
        self.high = data.get('high', 0.0)
        self.low = data.get('low', 0.0)
        self.volume = data.get('volume', 0.0)
        self.money = data.get('money', 0.0)  # Amount traded
    
    def mavg(self, n: int, field: str = 'close') -> float:
        """
        Calculate moving average
        Note: This is a simplified version, actual implementation would query historical data
        """
        return self._data.get(field, 0.0)
    
    def vwap(self, n: int) -> float:
        """
        Calculate volume-weighted average price
        Note: Simplified version
        """
        if self.volume > 0:
            return self.money / self.volume
        return self.close


class DataProxy:
    """
    Data proxy object providing access to current bar data
    """
    def __init__(self):
        self._securities: dict[str, SecurityData] = {}
    
    def __getitem__(self, security: str) -> SecurityData:
        """Get data for a security"""
        if security not in self._securities:
            # Return empty data if not available
            self._securities[security] = SecurityData(security, {})
        return self._securities[security]
    
    def __setitem__(self, security: str, data: SecurityData) -> None:
        """Set data for a security"""
        self._securities[security] = data
    
    def __contains__(self, security: str) -> bool:
        """Check if security data is available"""
        return security in self._securities


class DataAPI:
    """
    Container for data API functions
    """
    
    def __init__(self, strategy):
        self.strategy = strategy
    
    def history(
        self,
        count: int,
        unit: str = '1d',
        field: Union[str, List[str]] = 'close',
        security_list: Optional[List[str]] = None,
        df: bool = True,
        skip_paused: bool = True,
        fq: str = 'pre',
    ) -> Union[pd.DataFrame, dict]:
        """
        Get historical data for multiple securities
        
        Args:
            count: Number of bars
            unit: Time unit ('1d', '1m', etc.)
            field: Field name or list of fields
            security_list: List of securities (None = all in universe)
            df: Return DataFrame (True) or dict (False)
            skip_paused: Skip suspended stocks
            fq: Adjustment type ('pre', 'post', 'none')
        
        Returns:
            DataFrame with multi-index or dict
        """
        if security_list is None:
            security_list = self.strategy.context.universe
        
        if isinstance(field, str):
            field = [field]
        
        # Get data from strategy
        return self.strategy.get_history_data(
            securities=security_list,
            count=count,
            unit=unit,
            fields=field,
            skip_paused=skip_paused,
            fq=fq,
        )
    
    def attribute_history(
        self,
        security: str,
        count: int,
        unit: str = '1d',
        fields: Optional[List[str]] = None,
        df: bool = True,
        skip_paused: bool = True,
        fq: str = 'pre',
    ) -> pd.DataFrame:
        """
        Get historical data for a single security
        
        Args:
            security: Security code
            count: Number of bars
            unit: Time unit
            fields: List of fields
            df: Return DataFrame
            skip_paused: Skip suspended periods
            fq: Adjustment type
        
        Returns:
            DataFrame with requested fields
        """
        if fields is None:
            fields = ['close']
        
        return self.strategy.get_history_data(
            securities=[security],
            count=count,
            unit=unit,
            fields=fields,
            skip_paused=skip_paused,
            fq=fq,
        )
    
    def get_price(
        self,
        security: Union[str, List[str]],
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        frequency: str = 'daily',
        fields: Optional[List[str]] = None,
        skip_paused: bool = False,
        fq: str = 'pre',
        count: Optional[int] = None,
    ) -> Union[pd.DataFrame, pd.Series]:
        """
        Get price data for securities
        
        Args:
            security: Security code or list
            start_date: Start date
            end_date: End date
            frequency: 'daily' or 'minute'
            fields: List of fields
            skip_paused: Skip suspended stocks
            fq: Adjustment type
            count: Number of bars (alternative to dates)
        
        Returns:
            DataFrame or Series with price data
        """
        if isinstance(security, str):
            securities = [security]
        else:
            securities = security
        
        if fields is None:
            fields = ['close']
        
        # Convert dates to datetime if needed
        if start_date:
            start_date = pd.to_datetime(start_date)
        if end_date:
            end_date = pd.to_datetime(end_date)
        
        return self.strategy.get_price_data(
            securities=securities,
            start_date=start_date,
            end_date=end_date,
            fields=fields,
            frequency=frequency,
            skip_paused=skip_paused,
            fq=fq,
            count=count,
        )
    
    def get_fundamentals(
        self,
        query_object,
        date: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Get fundamental data (财务数据)
        
        Args:
            query_object: Query object (e.g., query(valuation))
            date: Query date
        
        Returns:
            DataFrame with fundamental data
        """
        # Placeholder - would integrate with fundamental data source
        return pd.DataFrame()
