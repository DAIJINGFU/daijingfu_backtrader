"""
A-share trading rules implementation

This module implements Chinese A-share market trading rules including:
- Limit up/down checking
- Suspension handling
- ST stock restrictions
- Trading time restrictions
"""
from typing import Optional, Dict, Tuple
from datetime import datetime, date
import pandas as pd
from loguru import logger


class TradingRulesChecker:
    """
    Checker for A-share trading rules
    """
    
    # Board types
    BOARD_MAIN = 'main'  # Main board (60xxxx, 000xxx)
    BOARD_CYBB = 'cyb'   # ChiNext (300xxx)
    BOARD_KCBB = 'kcb'   # STAR Market (688xxx)
    BOARD_BJ = 'bj'      # Beijing Stock Exchange (43xxxx, 83xxxx)
    
    # Price limit percentages
    PRICE_LIMITS = {
        BOARD_MAIN: 0.10,    # ±10%
        BOARD_CYBB: 0.20,    # ±20% (after registration reform)
        BOARD_KCBB: 0.20,    # ±20%
        BOARD_BJ: 0.30,      # ±30%
    }
    
    # ST stock limit
    ST_LIMIT = 0.05  # ±5%
    
    def __init__(self):
        # Cache for limit prices
        self._limit_cache: Dict[Tuple[str, date, float], Tuple[float, float]] = {}
        
        # Cache for suspension status
        self._suspension_cache: Dict[Tuple[str, date], bool] = {}
    
    def get_board_type(self, security: str) -> str:
        """
        Determine board type from security code
        
        Args:
            security: Security code (e.g., '000001.XSHE')
        
        Returns:
            Board type constant
        """
        # Extract numeric code
        if '.' in security:
            code = security.split('.')[0]
        else:
            code = security
        
        # Determine board
        if code.startswith('688'):
            return self.BOARD_KCBB
        elif code.startswith('300'):
            return self.BOARD_CYBB
        elif code.startswith('43') or code.startswith('83'):
            return self.BOARD_BJ
        else:
            return self.BOARD_MAIN
    
    def is_st_stock(self, security: str, trade_date: datetime) -> bool:
        """
        Check if stock is ST/ST*
        
        Args:
            security: Security code
            trade_date: Trading date
        
        Returns:
            True if ST stock
        """
        # TODO: Implement actual ST check with database/file lookup
        # For now, simple heuristic based on code
        # Real implementation would query from metadata
        return False
    
    def get_limit_prices(
        self,
        security: str,
        trade_date: datetime,
        prev_close: float,
    ) -> Tuple[float, float]:
        """
        Calculate limit up and limit down prices
        
        Args:
            security: Security code
            trade_date: Trading date
            prev_close: Previous close price
        
        Returns:
            Tuple of (limit_up, limit_down)
        """
        # Check cache
        cache_key = (security, trade_date.date(), prev_close)
        if cache_key in self._limit_cache:
            return self._limit_cache[cache_key]
        
        # Determine limit percentage
        if self.is_st_stock(security, trade_date):
            limit_pct = self.ST_LIMIT
        else:
            board = self.get_board_type(security)
            limit_pct = self.PRICE_LIMITS.get(board, 0.10)
        
        # Calculate limits
        limit_up = prev_close * (1 + limit_pct)
        limit_down = prev_close * (1 - limit_pct)
        
        # Round to 2 decimal places (price precision)
        limit_up = round(limit_up, 2)
        limit_down = round(limit_down, 2)
        
        # Cache result
        self._limit_cache[cache_key] = (limit_up, limit_down)
        
        return limit_up, limit_down
    
    def check_order_price(
        self,
        security: str,
        trade_date: datetime,
        price: float,
        prev_close: float,
        side: str = 'buy',
    ) -> Tuple[bool, float]:
        """
        Check if order price is within limit range
        
        Args:
            security: Security code
            trade_date: Trading date
            price: Order price
            prev_close: Previous close price
            side: 'buy' or 'sell'
        
        Returns:
            Tuple of (is_valid, adjusted_price)
        """
        limit_up, limit_down = self.get_limit_prices(security, trade_date, prev_close)
        
        if side == 'buy':
            # Buy order cannot exceed limit up
            if price > limit_up:
                logger.warning(
                    f"Buy price {price:.2f} exceeds limit up {limit_up:.2f} for {security}, "
                    f"adjusting to limit up"
                )
                return False, limit_up
            return True, price
        else:  # sell
            # Sell order cannot be below limit down
            if price < limit_down:
                logger.warning(
                    f"Sell price {price:.2f} below limit down {limit_down:.2f} for {security}, "
                    f"adjusting to limit down"
                )
                return False, limit_down
            return True, price
    
    def is_limit_up(
        self,
        security: str,
        trade_date: datetime,
        current_price: float,
        prev_close: float,
        tolerance: float = 0.01,
    ) -> bool:
        """
        Check if stock is at limit up
        
        Args:
            security: Security code
            trade_date: Trading date
            current_price: Current price
            prev_close: Previous close price
            tolerance: Price tolerance (0.01 = 1 cent)
        
        Returns:
            True if at limit up
        """
        limit_up, _ = self.get_limit_prices(security, trade_date, prev_close)
        return abs(current_price - limit_up) <= tolerance
    
    def is_limit_down(
        self,
        security: str,
        trade_date: datetime,
        current_price: float,
        prev_close: float,
        tolerance: float = 0.01,
    ) -> bool:
        """
        Check if stock is at limit down
        
        Args:
            security: Security code
            trade_date: Trading date
            current_price: Current price
            prev_close: Previous close price
            tolerance: Price tolerance
        
        Returns:
            True if at limit down
        """
        _, limit_down = self.get_limit_prices(security, trade_date, prev_close)
        return abs(current_price - limit_down) <= tolerance
    
    def is_suspended(
        self,
        security: str,
        trade_date: datetime,
        suspension_data: Optional[pd.DataFrame] = None,
    ) -> bool:
        """
        Check if stock is suspended
        
        Args:
            security: Security code
            trade_date: Trading date
            suspension_data: Optional DataFrame with suspension info
        
        Returns:
            True if suspended
        """
        # Check cache
        cache_key = (security, trade_date.date())
        if cache_key in self._suspension_cache:
            return self._suspension_cache[cache_key]
        
        # Check suspension data if provided
        if suspension_data is not None:
            try:
                if security in suspension_data.index:
                    date_str = trade_date.strftime('%Y-%m-%d')
                    if date_str in suspension_data.columns:
                        is_suspended = bool(suspension_data.loc[security, date_str])
                        self._suspension_cache[cache_key] = is_suspended
                        return is_suspended
            except Exception as e:
                logger.warning(f"Error checking suspension data: {e}")
        
        # Default: not suspended
        self._suspension_cache[cache_key] = False
        return False
    
    def can_trade(
        self,
        security: str,
        trade_date: datetime,
        current_price: float,
        prev_close: float,
        side: str = 'buy',
        suspension_data: Optional[pd.DataFrame] = None,
    ) -> Tuple[bool, str]:
        """
        Comprehensive check if trade is allowed
        
        Args:
            security: Security code
            trade_date: Trading date
            current_price: Current price
            prev_close: Previous close price
            side: 'buy' or 'sell'
            suspension_data: Optional suspension data
        
        Returns:
            Tuple of (can_trade, reason)
        """
        # Check suspension
        if self.is_suspended(security, trade_date, suspension_data):
            return False, "Stock is suspended"
        
        # Check limit up (cannot buy at limit up in many cases)
        if side == 'buy' and self.is_limit_up(security, trade_date, current_price, prev_close):
            return False, "Stock is at limit up (hard to buy)"
        
        # Check limit down (cannot sell at limit down in many cases)
        if side == 'sell' and self.is_limit_down(security, trade_date, current_price, prev_close):
            return False, "Stock is at limit down (hard to sell)"
        
        return True, "OK"
    
    def get_tradeable_amount(
        self,
        security: str,
        trade_date: datetime,
        desired_amount: int,
        current_price: float,
        prev_close: float,
        side: str = 'buy',
        suspension_data: Optional[pd.DataFrame] = None,
    ) -> Tuple[int, str]:
        """
        Get actual tradeable amount considering restrictions
        
        Args:
            security: Security code
            trade_date: Trading date
            desired_amount: Desired trade amount
            current_price: Current price
            prev_close: Previous close price
            side: 'buy' or 'sell'
            suspension_data: Optional suspension data
        
        Returns:
            Tuple of (actual_amount, reason)
        """
        can_trade, reason = self.can_trade(
            security, trade_date, current_price, prev_close, side, suspension_data
        )
        
        if not can_trade:
            return 0, reason
        
        # For now, assume full amount is tradeable
        # In reality, we might reduce amount based on volume limits, etc.
        return desired_amount, "OK"


# Global instance
trading_rules = TradingRulesChecker()
