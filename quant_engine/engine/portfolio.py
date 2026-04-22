import logging
from typing import Dict, List, Optional
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)


class PortfolioManager:
    """
    Portfolio allocation engine.
    Rebalances capital every N seconds based on health scores.
    """
    
    def __init__(self, config: dict, scoring_engine):
        self.config = config
        self.scoring_engine = scoring_engine
        
        # Portfolio config
        self.portfolio_config = config.get("portfolio", {})
        self.rebalance_interval = self.portfolio_config.get("rebalance_interval_sec", 5)
        self.capital_concentration_limit = self.portfolio_config.get("capital_concentration_limit", 0.25)
        
        # Portfolio state
        self.total_capital = 100000.0  # Starting capital
        self.allocations: Dict[str, float] = {}  # symbol -> allocated capital
        self.positions: Dict[str, dict] = {}  # symbol -> position info
        self.last_rebalance_time = 0
        
        # Callbacks
        self.on_rebalance_callback = None
        
    def set_total_capital(self, capital: float):
        """Update total capital."""
        self.total_capital = capital
        logger.info(f"Total capital updated to ${capital:,.2f}")
        
    def calculate_allocations(self, health_scores: Dict[str, float]) -> Dict[str, float]:
        """
        Calculate capital allocations based on health scores.
        Capital flows to top 20-60 coins based on scores.
        """
        if not health_scores:
            return {}
            
        # Sort by health score
        sorted_symbols = sorted(
            health_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Select top symbols (top 20-60 based on score distribution)
        top_symbols = []
        for symbol, score in sorted_symbols:
            if score > 0.5:  # Only allocate to symbols with decent health
                top_symbols.append((symbol, score))
                if len(top_symbols) >= 60:  # Max 60 active positions
                    break
                    
        if not top_symbols:
            return {}
            
        # Calculate weights based on health scores
        total_score = sum(score for _, score in top_symbols)
        weights = {
            symbol: score / total_score
            for symbol, score in top_symbols
        }
        
        # Apply concentration limit
        max_allocation = self.total_capital * self.capital_concentration_limit
        allocations = {}
        
        for symbol, weight in weights.items():
            raw_allocation = self.total_capital * weight
            capped_allocation = min(raw_allocation, max_allocation)
            allocations[symbol] = capped_allocation
            
        # Normalize if we hit concentration limits
        total_allocated = sum(allocations.values())
        if total_allocated < self.total_capital:
            # Scale up to use all capital
            scale_factor = self.total_capital / total_allocated
            for symbol in allocations:
                allocations[symbol] *= scale_factor
                
        return allocations
        
    async def rebalance(self, health_scores: Dict[str, float]):
        """Rebalance portfolio based on current health scores."""
        current_time = datetime.now().timestamp()
        
        # Check if rebalance is needed
        if current_time - self.last_rebalance_time < self.rebalance_interval:
            return
            
        self.last_rebalance_time = current_time
        
        # Calculate new allocations
        new_allocations = self.calculate_allocations(health_scores)
        
        # Log rebalance
        logger.info(f"Rebalancing portfolio: {len(new_allocations)} active positions")
        
        # Update allocations
        self.allocations = new_allocations
        
        # Trigger callback
        if self.on_rebalance_callback:
            await self.on_rebalance_callback(new_allocations)
            
    def get_allocation(self, symbol: str) -> float:
        """Get current allocation for symbol."""
        return self.allocations.get(symbol, 0.0)
        
    def get_all_allocations(self) -> Dict[str, float]:
        """Get all current allocations."""
        return self.allocations.copy()
        
    def update_position(self, symbol: str, position_info: dict):
        """Update position information for symbol."""
        self.positions[symbol] = position_info
        
    def get_position(self, symbol: str) -> Optional[dict]:
        """Get position information for symbol."""
        return self.positions.get(symbol)
        
    def get_total_exposure(self) -> float:
        """Calculate total portfolio exposure."""
        return sum(self.allocations.values())
        
    def get_allocation_summary(self) -> dict:
        """Get summary of current allocations."""
        return {
            "total_capital": self.total_capital,
            "total_allocated": self.get_total_exposure(),
            "num_positions": len(self.allocations),
            "top_positions": sorted(
                self.allocations.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
        }
        
    def set_rebalance_callback(self, callback):
        """Set callback for rebalance events."""
        self.on_rebalance_callback = callback
