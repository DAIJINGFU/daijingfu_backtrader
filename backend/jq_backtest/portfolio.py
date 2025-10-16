"""
Portfolio and Position objects for JoinQuant-compatible strategies
"""
from typing import Dict, Optional


class Position:
    """
    Position object representing a holding in a security
    """
    def __init__(self, security: str):
        self.security = security
        self.total_amount: int = 0  # Total position size
        self.closeable_amount: int = 0  # Amount that can be sold (T+1 rule)
        self.avg_cost: float = 0.0  # Average cost per share
        self.price: float = 0.0  # Current price
        self.value: float = 0.0  # Current value of position
        self.pnl: float = 0.0  # Profit/loss
        
        # Today's bought amount (for T+1 rule)
        self.today_amount: int = 0
    
    def update_price(self, price: float) -> None:
        """Update current price and derived values"""
        self.price = price
        self.value = self.total_amount * price
        if self.total_amount > 0:
            self.pnl = (price - self.avg_cost) * self.total_amount
        else:
            self.pnl = 0.0
    
    def add_amount(self, amount: int, price: float, is_today: bool = True) -> None:
        """Add to position (buy)"""
        if amount <= 0:
            return
        
        # Update average cost
        if self.total_amount > 0:
            total_cost = self.avg_cost * self.total_amount + price * amount
            self.total_amount += amount
            self.avg_cost = total_cost / self.total_amount
        else:
            self.total_amount = amount
            self.avg_cost = price
        
        # Update today's amount for T+1 rule
        if is_today:
            self.today_amount += amount
        else:
            self.closeable_amount += amount
        
        self.update_price(price)
    
    def reduce_amount(self, amount: int, price: float) -> None:
        """Reduce position (sell)"""
        if amount <= 0:
            return
        
        amount = min(amount, self.total_amount)
        self.total_amount -= amount
        self.closeable_amount = max(0, self.closeable_amount - amount)
        
        if self.total_amount == 0:
            self.avg_cost = 0.0
            self.closeable_amount = 0
            self.today_amount = 0
        
        self.update_price(price)
    
    def on_new_day(self) -> None:
        """Called at the start of a new day - convert today's amount to closeable"""
        self.closeable_amount += self.today_amount
        self.today_amount = 0


class Portfolio:
    """
    Portfolio object representing the account and all holdings
    """
    def __init__(self, starting_cash: float = 1000000):
        self.starting_cash = starting_cash
        self.total_value: float = starting_cash
        self.available_cash: float = starting_cash
        self.positions_value: float = 0.0
        self.positions: Dict[str, Position] = {}
        
        # Performance metrics
        self.returns: float = 0.0
        self.pnl: float = 0.0
    
    @property
    def cash(self) -> float:
        """Alias for available_cash (JoinQuant compatibility)"""
        return self.available_cash
    
    def update_value(self) -> None:
        """Update total value based on cash and positions"""
        self.positions_value = sum(pos.value for pos in self.positions.values())
        self.total_value = self.available_cash + self.positions_value
        self.returns = (self.total_value - self.starting_cash) / self.starting_cash
        self.pnl = self.total_value - self.starting_cash
    
    def get_position(self, security: str) -> Position:
        """Get position for a security (creates if doesn't exist)"""
        if security not in self.positions:
            self.positions[security] = Position(security)
        return self.positions[security]
    
    def on_new_day(self) -> None:
        """Called at the start of a new day"""
        for position in self.positions.values():
            position.on_new_day()
