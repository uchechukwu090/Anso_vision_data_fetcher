import websocket
import json
import threading

SUPABASE_REALTIME_URL = "wss://qqsxwhmryfzvrugbqzks.supabase.co/realtime/v1/websocket"
SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")

def on_watchlist_update(ws, message):
    data = json.loads(message)
    if data.get("event") in ["INSERT", "UPDATE", "DELETE"]:
        print("🔄 Watchlist changed — refreshing symbols...")
        refresh_symbols()

def subscribe_to_watchlist():
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
