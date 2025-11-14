import websocket, json, threading, time, requests
from candle_aggregator import add_tick, get_candles

API_KEY = "fef3c30aa26c4831924fdb142f87550d"
SYMBOLS = ["EUR/USD", "BTC/USD"]
BACKEND_URL = "https://anso-vision-backend.onrender.com/webhook/live"

def on_message(ws, message):
    data = json.loads(message)
    if "symbol" in data:
        add_tick(data["symbol"], float(data["price"]), int(data["timestamp"]))

def on_open(ws):
    ws.send(json.dumps({
        "action": "subscribe",
        "params": {"symbols": ",".join(SYMBOLS)}
    }))

def start_stream():
    def run():
        ws = websocket.WebSocketApp(
            f"wss://ws.twelvedata.com/v1/quotes/price?apikey={API_KEY}",
            on_message=on_message,
            on_open=on_open
        )
        ws.run_forever()

    threading.Thread(target=run).start()

    while True:
        time.sleep(60)
        for symbol in SYMBOLS:
            candles = get_candles(symbol)
            if candles:
                requests.post(BACKEND_URL, json={"symbol": symbol, "candles": candles})