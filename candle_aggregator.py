from collections import defaultdict
import time

buffers = defaultdict(list)
candles = defaultdict(list)

def add_tick(symbol, price, timestamp):
    minute = timestamp // 60
    buffers[symbol].append((minute, price))

def get_candles(symbol):
    now = int(time.time()) // 60
    ticks = [p for m, p in buffers[symbol] if m == now]
    if not ticks:
        return []

    o, h, l, c = ticks[0], max(ticks), min(ticks), ticks[-1]
    new_candle = {"time": now, "open": o, "high": h, "low": l, "close": c}
    candles[symbol].append(new_candle)
    if len(candles[symbol]) > 200:
        candles[symbol] = candles[symbol][-200:]
    return candles[symbol]