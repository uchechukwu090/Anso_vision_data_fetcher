import os
from fastapi import FastAPI
from websocket_client import start_stream, subscribe_to_watchlist
from news_checker import check_news

app = FastAPI()

@app.on_event("startup")
def startup_event():
    """
    Startup hook: automatically begin Supabase watchlist subscription
    and TwelveData WebSocket streaming when the service boots.
    """
    # 🔄 Listen for watchlist changes in Supabase
    subscribe_to_watchlist()
    # 📡 Start TwelveData WebSocket stream
    start_stream()

@app.get("/start")
def start_fetcher():
    """
    Manual trigger to restart the TwelveData stream if needed.
    """
    start_stream()
    return {"status": "WebSocket stream started"}

@app.get("/news")
def get_news():
    """
    Fetch latest impactful news from the news_checker module.
    """
    return check_news()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)
