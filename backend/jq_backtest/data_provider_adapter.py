"""
Adapter to expose a SimpleCSVDataProvider-like interface backed by
the migrated backtest_origin modules/s_2_data_loader implementations.

This keeps the engine API stable while switching the actual data source.
"""
from datetime import datetime
from typing import Optional

import pandas as pd

# Import the backtest_origin loader functions copied into jq_backtest/modules
from backend.jq_backtest.modules.s_2_data_loader import (
    load_price_dataframe,
    load_bt_feed,
)


class BacktestOriginDataProvider:
    """Provide a minimal load_data interface expected by CSVDataFeedAdapter.

    Methods:
        load_data(security, start_date, end_date, freq='daily', adjust='none') -> pd.DataFrame
    """

    def __init__(self, data_root: Optional[str] = None, stockdata_root: Optional[str] = None):
        self.data_root = data_root
        self.stockdata_root = stockdata_root

    def _to_datestr(self, d) -> str:
        if isinstance(d, datetime):
            return d.strftime("%Y-%m-%d")
        return str(d)

    def load_data(
        self,
        security: str,
        start_date,
        end_date,
        freq: str = "daily",
        adjust: str = "none",
        **_kwargs,
    ) -> pd.DataFrame:
        """Load data and return a pandas.DataFrame compatible with CSV adapter.

        start_date/end_date may be datetime or string.
        """
        start = self._to_datestr(start_date)
        end = self._to_datestr(end_date)

        # map adjustment terms to loader API expectations
        adj_map = {"pre": "pre", "post": "post", "none": "none", "auto": "auto", "qfq": "pre", "hfq": "post"}
        adj = adj_map.get(adjust, adjust)

        # call load_price_dataframe which returns a DataFrame
        df = load_price_dataframe(
            symbol=security,
            start=start,
            end=end,
            frequency=freq,
            adjust=adj,
            data_root=self.data_root,
            stockdata_root=self.stockdata_root,
        )

        return df
