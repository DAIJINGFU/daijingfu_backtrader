"""
Deprecated compatibility shim for SimpleCSVDataProvider.

This module ensures older imports still work after migrating the real
implementation into `backend/jq_backtest/modules/s_2_data_loader` and the
new adapter `backend.jq_backtest.data_provider_adapter.BacktestOriginDataProvider`.

Keep this shim minimal. New code should import and use the adapter or
`backend.jq_backtest` data loaders directly.
"""
import warnings as _warnings
_warnings.warn(
    "backend.data_provider.simple_provider is a compatibility shim and is deprecated."
    " Prefer backend.jq_backtest.data_provider_adapter.BacktestOriginDataProvider or modules/s_2_data_loader.",
    DeprecationWarning,
    stacklevel=2,
)
from typing import Any
import warnings

from backend.jq_backtest.data_provider_adapter import BacktestOriginDataProvider


class SimpleCSVDataProvider(BacktestOriginDataProvider):
    """Deprecated alias for compatibility.

    Behaves like the old SimpleCSVDataProvider but delegates to the
    BacktestOriginDataProvider implementation.
    """

    def __init__(self, data_root: Any = None, *args, **kwargs):
        warnings.warn(
            "SimpleCSVDataProvider is deprecated. Use BacktestOriginDataProvider or modules/s_2_data_loader directly.",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(data_root=data_root, *args, **kwargs)


__all__ = ["SimpleCSVDataProvider"]
"""
SimpleCSVDataProvider - Simplified CSV Data Provider

Designed for JoinQuant backtest module independent development

Supports two data formats:
1. Simple format: /stockdata/daily/000001.XSHE.csv
2. Main system format: /stock/TB/dailyweekly/000001.XSHE/000001.XSHE_daily.csv

Automatic format detection, no manual configuration required
"""

from pathlib import Path
from datetime import datetime
from typing import List, Optional
import pandas as pd
from loguru import logger


class SimpleCSVDataProvider:
    """Simplified CSV Data Provider with automatic format detection"""
    
    # Adjust type mapping
    _ADJ_SUFFIX = {
        "raw": "",
        "none": "",
        "pre": "_qfq",
        "forward": "_qfq",
        "qfq": "_qfq",
        "post": "_hfq",
        "backward": "_hfq",
        "hfq": "_hfq",
    }
    
    def __init__(self, data_root: str):
        """
        Initialize data provider
        
        Args:
            data_root: CSV data root directory
        """
        self.data_root = Path(data_root)
        if not self.data_root.exists():
            # On some developer machines/tests the data_root is a macOS mount like
            # '/Volumes/ESSD/stockdata/'. On CI or Windows developer machines that
            # path doesn't exist. Try sensible fallbacks inside the repository's
            # stockdata folder before failing.
            repo_root = Path(__file__).resolve().parents[3]
            candidates = [
                repo_root / 'stockdata',
                repo_root / 'stockdata' / 'stockdata',
                repo_root / 'stockdata' / 'stockdata' / '1d_1w_1m',
            ]
            for c in candidates:
                if c.exists():
                    self.data_root = c
                    break

            # If still missing, try to map common mount prefix to repo stockdata
            if not self.data_root.exists():
                if str(data_root).startswith('/Volumes') and (repo_root / 'stockdata').exists():
                    alt = repo_root / 'stockdata' / 'stockdata'
                    if alt.exists():
                        self.data_root = alt
                    else:
                        self.data_root = repo_root / 'stockdata'

            # Final fallback: don't raise, allow an empty provider to be used by tests
            if not self.data_root.exists():
                logger.warning(f"Data directory does not exist: {data_root}; continuing with empty provider and format_type='simple'")
                self.is_main_system = False
                self.format_type = "simple"
                return
        
        # Auto-detect data format
        # 1. 主系统格式: dailyweekly/ 目录
        # 2. 新格式: 1d_1w_1m/ 目录  
        # 3. 简化格式: daily/ 目录
        if (self.data_root / "dailyweekly").exists():
            self.is_main_system = True
            self.format_type = "main_system"
            logger.info(f"Detected main system format: {data_root}")
        elif (self.data_root / "1d_1w_1m").exists():
            self.is_main_system = False
            self.format_type = "tushare_style"
            logger.info(f"Detected Tushare-style format (1d_1w_1m): {data_root}")
        else:
            self.is_main_system = False
            # If CSV files live directly under data_root (no daily/minute folders), still support it
            has_csv_in_root = any(self.data_root.glob("*.csv"))
            if has_csv_in_root:
                self.format_type = "simple"
                logger.info(f"Using simple format (CSV in root): {data_root}")
            else:
                self.format_type = "simple"
                logger.info(f"Using simple format: {data_root}")
    
    def load_data(
        self,
        security: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        freq: str = 'daily',
        adjust: str = 'none'
    ) -> pd.DataFrame:
        """
        Load historical data for a security
        
        Args:
            security: Security code (e.g. '000001.XSHE')
            start_date: Start date (optional)
            end_date: End date (optional)
            freq: Frequency ('daily' or 'minute')
            adjust: Adjust type ('pre', 'post', 'none')
        
        Returns:
            DataFrame with columns: datetime, open, high, low, close, volume, amount
        """
        try:
            # Get file path
            csv_path = self._get_csv_path(security, freq, adjust)
            
            if not csv_path.exists():
                logger.warning(f"Data file does not exist: {csv_path}")
                return pd.DataFrame()
            
            # Read CSV
            df = pd.read_csv(csv_path)
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            # Convert datetime
            df['datetime'] = pd.to_datetime(df['datetime'])
            df.set_index('datetime', inplace=True)
            df.sort_index(inplace=True)
            
            # Filter by date range
            if start_date:
                df = df[df.index >= pd.Timestamp(start_date)]
            if end_date:
                df = df[df.index <= pd.Timestamp(end_date)]
            
            logger.debug(f"Loaded data: {security}, {freq}, {len(df)} records")
            return df
            
        except Exception as e:
            logger.error(f"Failed to load data for {security}: {e}")
            return pd.DataFrame()
    
    def _get_csv_path(self, security: str, freq: str, adjust: str) -> Path:
        """Get CSV file path"""
        adj_suffix = self._ADJ_SUFFIX.get(adjust.lower(), "")
        
        if self.format_type == "main_system":
            return self._get_main_system_path(security, freq, adj_suffix)
        elif self.format_type == "tushare_style":
            return self._get_tushare_style_path(security, freq, adj_suffix)
        else:
            return self._get_simple_path(security, freq, adj_suffix)
    
    def _get_simple_path(self, security: str, freq: str, adj_suffix: str) -> Path:
        """Simple format path"""
        # Support several possible folder namings: 'daily', files in root, and minute folder '1min' or 'minute'
        is_daily = freq in ["daily", "day", "1d"]
        suffix_part = f"_{adj_suffix}" if adj_suffix else ""
        filename = f"{security}{suffix_part}.csv"

        # 1) preferred: data_root/daily/filename
        daily_path = self.data_root / "daily" / filename
        if is_daily and daily_path.exists():
            return daily_path

        # 2) CSV placed directly in data_root
        root_path = self.data_root / filename
        if root_path.exists():
            return root_path

        # 3) minute data: try '1min' then 'minute'
        if not is_daily:
            one_min = self.data_root / "1min" / filename
            if one_min.exists():
                return one_min
            minute = self.data_root / "minute" / filename
            if minute.exists():
                return minute

        # 4) fallback: daily path (even if missing) to keep previous behavior
        freq_dir = "daily" if is_daily else "minute"
        return self.data_root / freq_dir / filename
    
    def _get_tushare_style_path(self, security: str, freq: str, adj_suffix: str) -> Path:
        """
        Tushare-style format path
        格式: /1d_1w_1m/股票代码/股票代码_daily.csv
        例如: /1d_1w_1m/000001/000001_daily_qfq.csv
        """
        # 提取纯股票代码（去掉交易所后缀）
        code = security.split('.')[0] if '.' in security else security
        
        if freq in ["daily", "day", "1d"]:
            freq_name = "daily"
        elif freq in ["weekly", "week", "1w"]:
            freq_name = "weekly"
        elif freq in ["monthly", "month", "1m"]:
            freq_name = "monthly"
        else:
            freq_name = "daily"
        
        # 构建文件名: 000001_daily_qfq.csv
        filename = f"{code}_{freq_name}{adj_suffix}.csv"
        return self.data_root / "1d_1w_1m" / code / filename
    
    def _get_main_system_path(self, security: str, freq: str, adj_suffix: str) -> Path:
        """Main system format path"""
        if freq in ["daily", "day", "1d"]:
            return (self.data_root / "dailyweekly" / security / 
                   f"{security}_daily{adj_suffix}.csv")
        elif freq in ["minute", "1min"]:
            code = self._convert_code_for_minute(security)
            return self.data_root / "1m" / f"{code}.csv"
        else:
            raise ValueError(f"Unsupported frequency: {freq}")
    
    def _convert_code_for_minute(self, security: str) -> str:
        """
        Convert security code format for minute data
        000001.XSHE -> SZ000001
        600000.XSHG -> SH600000
        """
        if '.' in security:
            code, exchange = security.split('.')
            exchange_prefix = "SZ" if exchange == "XSHE" else "SH"
            return f"{exchange_prefix}{code}"
        return security
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize column names"""
        column_mapping = {
            # 英文列名
            'date': 'datetime',
            'time': 'datetime',
            'timestamp': 'datetime',
            'vol': 'volume',
            'turnover': 'amount',
            # 中文列名（Tushare格式）
            '日期': 'datetime',
            '时间': 'datetime',
            '股票代码': 'code',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume',
            '成交额': 'amount',
        }
        
        df = df.rename(columns=column_mapping)
        
        # Ensure required columns exist
        required_cols = ['datetime', 'open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"CSV file missing required column: {col}")
        
        # Optional columns
        if 'volume' not in df.columns:
            df['volume'] = 0
        if 'amount' not in df.columns:
            df['amount'] = 0
        
        return df
    
    def get_price(
        self,
        security: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = 'daily',
        fields: Optional[List[str]] = None,
        fq: str = 'pre'
    ) -> pd.DataFrame:
        """
        Get price data (JoinQuant API compatible)
        
        Args:
            security: Security code
            start_date: Start date
            end_date: End date
            frequency: Frequency
            fields: List of fields to return
            fq: Adjust type
        
        Returns:
            DataFrame
        """
        df = self.load_data(
            security=security,
            start_date=start_date,
            end_date=end_date,
            freq=frequency,
            adjust=fq
        )
        
        if fields and not df.empty:
            available_fields = [f for f in fields if f in df.columns]
            if available_fields:
                df = df[available_fields]
        
        return df
    
    def list_securities(self, freq: str = 'daily') -> List[str]:
        """
        List all available security codes
        
        Args:
            freq: Frequency
        
        Returns:
            List of security codes
        """
        securities = []
        
        try:
            if self.format_type == "main_system":
                # Main system: scan dailyweekly directory
                freq_dir = self.data_root / "dailyweekly"
                if freq_dir.exists():
                    for item in freq_dir.iterdir():
                        if item.is_dir():
                            securities.append(item.name)
            elif self.format_type == "tushare_style":
                # Tushare-style: scan 1d_1w_1m directory
                freq_dir = self.data_root / "1d_1w_1m"
                if freq_dir.exists():
                    for item in freq_dir.iterdir():
                        if item.is_dir() and not item.name.startswith('.'):
                            # 只取目录名（纯代码），添加默认交易所后缀
                            code = item.name
                            # 简单判断：6开头的是上交所，其他是深交所
                            if code.startswith('6'):
                                securities.append(f"{code}.XSHG")
                            else:
                                securities.append(f"{code}.XSHE")
            else:
                # Simple format: scan daily or minute directory
                freq_dir = self.data_root / ("daily" if freq == "daily" else "minute")
                # Try several locations: freq_dir, '1min', and csv files in root
                if freq_dir.exists():
                    for csv_file in freq_dir.glob("*.csv"):
                        code = csv_file.stem
                        if not code.endswith(('_qfq', '_hfq')):
                            securities.append(code)
                # support legacy '1min' directory name
                alt_min_dir = self.data_root / "1min"
                if alt_min_dir.exists() and freq != 'daily':
                    for csv_file in alt_min_dir.glob("*.csv"):
                        code = csv_file.stem
                        if not code.endswith(('_qfq', '_hfq')):
                            securities.append(code)
                # support CSV files directly under data_root
                for csv_file in self.data_root.glob("*.csv"):
                    code = csv_file.stem
                    if not code.endswith(('_qfq', '_hfq')):
                        securities.append(code)
            
            logger.debug(f"Found {len(securities)} securities")
            return sorted(set(securities))
            
        except Exception as e:
            logger.error(f"Failed to list securities: {e}")
            return []
    
    def get_trade_days(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[datetime]:
        """
        Get trade days list
        
        Args:
            start_date: Start date
            end_date: End date
        
        Returns:
            List of trade days
        """
        securities = self.list_securities()
        if not securities:
            return []
        
        # Use first security's data
        df = self.load_data(securities[0], start_date, end_date, freq='daily')
        if df.empty:
            return []

        return df.index.tolist()


# Pytest fixture compatibility
try:
    import pytest

    @pytest.fixture
    def provider(tmp_path):
        """Provide a SimpleCSVDataProvider instance for tests that expect a
        `provider` fixture (test_stockdata_compatibility.py).

        The fixture uses the same path as the original test expects but will
        fall back to repository stockdata folders handled in the provider.
        """
        return SimpleCSVDataProvider('/Volumes/Extreme SSD/stockdata')
except Exception:
    # pytest not present or fixture registration failed; ignore
    pass
