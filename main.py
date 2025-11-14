import os
from fastapi import FastAPI
from websocket_client import start_stream
from news_checker import check_news

app = FastAPI()

@app.get("/start")
def start_fetcher():
    start_stream()
    return {"status": "WebSocket stream started"}

@app.get("/news")
def get_news():
    return check_news()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main:app", host="0.0.0.0", port=port)