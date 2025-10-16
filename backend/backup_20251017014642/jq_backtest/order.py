"""
Order objects for JoinQuant-compatible strategies
"""
from enum import Enum
from typing import Optional
from datetime import datetime


class OrderStatus(Enum):
    """Order status"""
    OPEN = 'open'
    FILLED = 'filled'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'


class OrderStyle:
    """Base class for order styles"""
    pass


class MarketOrder(OrderStyle):
    """Market order - execute at market price"""
    def __repr__(self):
        return "MarketOrder()"


class LimitOrder(OrderStyle):
    """Limit order - execute at specified price or better"""
    def __init__(self, price: float):
        self.price = price
    
    def __repr__(self):
        return f"LimitOrder(price={self.price})"


class StopOrder(OrderStyle):
    """Stop order - execute when price reaches stop price"""
    def __init__(self, price: float):
        self.price = price
    
    def __repr__(self):
        return f"StopOrder(price={self.price})"


class Order:
    """
    Order object representing a trade order
    """
    def __init__(
        self,
        security: str,
        amount: int,
        style: Optional[OrderStyle] = None,
        side: str = 'long',
        pindex: int = 0,
    ):
        self.security = security
        self.amount = amount  # Positive for buy, negative for sell
        self.style = style or MarketOrder()
        self.side = side  # 'long' or 'short'
        self.pindex = pindex  # Portfolio index
        
        # Order state
        self.status = OrderStatus.OPEN
        self.filled: int = 0  # Amount filled so far
        self.price: Optional[float] = None  # Actual execution price
        self.commission: float = 0.0  # Commission paid
        
        # Timestamps
        self.add_time: Optional[datetime] = None
        self.filled_time: Optional[datetime] = None
        
        # Order ID
        self.order_id: Optional[str] = None
    
    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order"""
        return self.amount > 0
    
    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order"""
        return self.amount < 0
    
    def __repr__(self):
        action = 'BUY' if self.is_buy else 'SELL'
        return (f"Order({action} {abs(self.amount)} of {self.security}, "
                f"status={self.status.value}, style={self.style})")
