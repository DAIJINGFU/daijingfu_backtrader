"""
Trading API functions for JoinQuant-compatible strategies
"""
from typing import Optional
from backend.jq_backtest.order import Order, OrderStyle, MarketOrder


class TradingAPI:
    """
    Container for trading API functions
    These functions will be injected into the strategy execution context
    """
    
    def __init__(self, strategy):
        self.strategy = strategy
    
    def order(
        self,
        security: str,
        amount: int,
        style: Optional[OrderStyle] = None,
        side: str = 'long',
        pindex: int = 0,
        close_today: bool = False,
    ) -> Optional[Order]:
        """
        Place an order for a security
        
        Args:
            security: Security code
            amount: Number of shares (positive for buy, negative for sell)
            style: Order style (MarketOrder, LimitOrder, StopOrder)
            side: 'long' or 'short' (for futures)
            pindex: Portfolio index
            close_today: Close today's position first (for futures)
        
        Returns:
            Order object if successful, None otherwise
        """
        if amount == 0:
            return None
        
        # Round to 100 shares (A-share rule)
        if amount > 0:
            amount = (amount // 100) * 100
            if amount == 0:
                return None
        
        order_obj = Order(
            security=security,
            amount=amount,
            style=style or MarketOrder(),
            side=side,
            pindex=pindex,
        )
        
        return self.strategy.submit_order(order_obj)
    
    def order_target(
        self,
        security: str,
        amount: int,
        style: Optional[OrderStyle] = None,
        side: str = 'long',
        pindex: int = 0,
        close_today: bool = False,
    ) -> Optional[Order]:
        """
        Adjust position to target amount
        
        Args:
            security: Security code
            amount: Target position size
            style: Order style
            side: 'long' or 'short'
            pindex: Portfolio index
            close_today: Close today's position first
        
        Returns:
            Order object if successful, None otherwise
        """
        current_position = self.strategy.context.portfolio.get_position(security)
        current_amount = current_position.total_amount
        
        delta = amount - current_amount
        
        if delta == 0:
            return None
        
        return self.order(security, delta, style, side, pindex, close_today)
    
    def order_value(
        self,
        security: str,
        value: float,
        style: Optional[OrderStyle] = None,
        side: str = 'long',
        pindex: int = 0,
        close_today: bool = False,
    ) -> Optional[Order]:
        """
        Place an order for a certain value
        
        Args:
            security: Security code
            value: Target value in currency
            style: Order style
            side: 'long' or 'short'
            pindex: Portfolio index
            close_today: Close today's position first
        
        Returns:
            Order object if successful, None otherwise
        """
        # Get current price
        current_price = self.strategy.get_current_price(security)
        if current_price is None or current_price <= 0:
            return None
        
        # Calculate amount
        amount = int(value / current_price)
        
        return self.order(security, amount, style, side, pindex, close_today)
    
    def order_target_value(
        self,
        security: str,
        value: float,
        style: Optional[OrderStyle] = None,
        side: str = 'long',
        pindex: int = 0,
        close_today: bool = False,
    ) -> Optional[Order]:
        """
        Adjust position to target value
        
        Args:
            security: Security code
            value: Target value in currency
            style: Order style
            side: 'long' or 'short'
            pindex: Portfolio index
            close_today: Close today's position first
        
        Returns:
            Order object if successful, None otherwise
        """
        # Get current price
        current_price = self.strategy.get_current_price(security)
        if current_price is None or current_price <= 0:
            return None
        
        # Calculate target amount
        target_amount = int(value / current_price)
        
        return self.order_target(security, target_amount, style, side, pindex, close_today)
    
    def get_open_orders(self, security: Optional[str] = None) -> list[Order]:
        """
        Get all open orders
        
        Args:
            security: Filter by security (optional)
        
        Returns:
            List of open orders
        """
        return self.strategy.get_open_orders(security)
    
    def cancel_order(self, order: Order) -> bool:
        """
        Cancel an order
        
        Args:
            order: Order to cancel
        
        Returns:
            True if successful, False otherwise
        """
        return self.strategy.cancel_order(order)
