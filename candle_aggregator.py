"""
Real-time Candle Aggregator
Converts tick data to OHLC candles and triggers analysis
"""
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Callable
import logging

logger = logging.getLogger(__name__)


class CandleAggregator:
    """Aggregates real-time ticks into OHLC candles"""
    
    def __init__(self, timeframe_minutes: int = 60):
        self.timeframe_minutes = timeframe_minutes
        self.candles: Dict[str, List[Dict]] = {}  # symbol -> candles
        self.current_candle: Dict[str, Dict] = {}  # symbol -> current building candle
        self.on_candle_complete: Callable = None  # Callback when candle completes
        
        logger.info(f"✅ CandleAggregator initialized (timeframe: {timeframe_minutes}min)")
    
    def process_tick(self, symbol: str, price: float, timestamp: int):
        """Process incoming tick and aggregate into candles"""
        tick_time = datetime.fromtimestamp(timestamp)
        
        # Initialize symbol if new
        if symbol not in self.candles:
            self.candles[symbol] = []
            self.current_candle[symbol] = None
        
        # Check if we need to start a new candle
        if self._should_start_new_candle(symbol, tick_time):
            self._complete_current_candle(symbol)
            self._start_new_candle(symbol, price, tick_time)
        
        # Update current candle
        self._update_current_candle(symbol, price)
    
    def _should_start_new_candle(self, symbol: str, tick_time: datetime) -> bool:
        """Check if current candle period has ended"""
        current = self.current_candle.get(symbol)
        
        if current is None:
            return True
        
        candle_start = current['start_time']
        candle_end = candle_start + timedelta(minutes=self.timeframe_minutes)
        
        return tick_time >= candle_end
    
    def _start_new_candle(self, symbol: str, price: float, tick_time: datetime):
        """Start a new candle"""
        # Round down to timeframe boundary
        minutes = (tick_time.minute // self.timeframe_minutes) * self.timeframe_minutes
        candle_start = tick_time.replace(minute=minutes, second=0, microsecond=0)
        
        self.current_candle[symbol] = {
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'start_time': candle_start,
            'symbol': symbol
        }
    
    def _update_current_candle(self, symbol: str, price: float):
        """Update current candle with new price"""
        candle = self.current_candle[symbol]
        candle['high'] = max(candle['high'], price)
        candle['low'] = min(candle['low'], price)
        candle['close'] = price
    
    def _complete_current_candle(self, symbol: str):
        """Complete current candle and trigger callback"""
        if self.current_candle.get(symbol) is None:
            return
        
        completed_candle = self.current_candle[symbol].copy()
        
        # Add to history
        self.candles[symbol].append(completed_candle)
        
        # Keep only last 250 candles
        if len(self.candles[symbol]) > 250:
            self.candles[symbol] = self.candles[symbol][-250:]
        
        logger.info(f"✅ Candle completed: {symbol} @ {completed_candle['close']:.2f} "
                   f"(O:{completed_candle['open']:.2f} H:{completed_candle['high']:.2f} "
                   f"L:{completed_candle['low']:.2f})")
        
        # Trigger callback if set
        if self.on_candle_complete and len(self.candles[symbol]) >= 250:
            asyncio.create_task(
                self.on_candle_complete(symbol, self.candles[symbol])
            )
    
    def get_candles(self, symbol: str, count: int = 250) -> List[Dict]:
        """Get historical candles for a symbol"""
        if symbol not in self.candles:
            return []
        
        return self.candles[symbol][-count:]
    
    def has_enough_data(self, symbol: str, required: int = 250) -> bool:
        """Check if symbol has enough candles for analysis"""
        return symbol in self.candles and len(self.candles[symbol]) >= required
