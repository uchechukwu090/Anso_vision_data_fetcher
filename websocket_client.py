import websocket
import json
import threading
import os
import time
import requests
from candle_aggregator import add_tick, get_candles
from supabase import create_client

# 🔐 Environment variables
SUPABASE_REALTIME_URL = f"{os.getenv('SUPABASE_URL')}/realtime/v1/websocket"
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "https://anso-vision-backend.onrender.com/webhook/live")
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Global symbol list
SYMBOLS = []

def refresh_symbols():
    """Reload symbols from Supabase watchlist table."""
    global SYMBOLS
    try:
        response = supabase.table("watchlist").select("symbol").execute()
        SYMBOLS = [item["symbol"] for item in response.data]
        print("✅ Watchlist refreshed:", SYMBOLS)
    except Exception as e:
        print("❌ Failed to refresh symbols:", e)

def on_watchlist_update(ws, message):
    data = json.loads(message)
    if data.get("event") in ["INSERT", "UPDATE", "DELETE"]:
        print("🔄 Watchlist changed — refreshing symbols...")
        refresh_symbols()

def subscribe_to_watchlist():
    """Subscribe to Supabase realtime watchlist changes."""
    def run():
        ws = websocket.WebSocketApp(
            f"{SUPABASE_REALTIME_URL}?apikey={SUPABASE_API_KEY}&vsn=1.0.0",
            on_message=on_watchlist_update
        )
        ws.on_open = lambda ws: ws.send(json.dumps({
            "topic": "realtime:public:watchlist",
            "event": "phx_join",
            "payload": {},
            "ref": "1"
        }))
        ws.run_forever()

    threading.Thread(target=run).start()

def handle_price_message(message):
    data = json.loads(message)
    if "symbol" in data:
        add_tick(data["symbol"], float(data["price"]), int(data["timestamp"]))

def subscribe_symbols(ws):
    if SYMBOLS:
        ws.send(json.dumps({
            "action": "subscribe",
            "params": {"symbols": ",".join(SYMBOLS)}
        }))
        print("📡 Subscribed to:", SYMBOLS)

def start_stream():
    """Start TwelveData WebSocket and push candles to backend."""
    def run():
        ws = websocket.WebSocketApp(
            f"wss://ws.twelvedata.com/v1/quotes/price?apikey={TWELVEDATA_API_KEY}",
            on_message=lambda ws, msg: handle_price_message(msg),
            on_open=lambda ws: subscribe_symbols(ws)
        )
        ws.run_forever()

    threading.Thread(target=run).start()

    while True:
        time.sleep(60)
        for symbol in SYMBOLS:
            candles = get_candles(symbol)
            if candles:
                requests.post(BACKEND_URL, json={"symbol": symbol, "candles": candles})
