import os
import uvicorn  # Import uvicorn at the top or inside the main block

from fastapi import FastAPI
# Assuming these modules exist in your environment
# from websocket_client import start_stream, subscribe_to_watchlist
# from news_checker import check_news

# Placeholder functions for missing imports, allowing the code to run standalone
def subscribe_to_watchlist():
    print("Subscribing to Supabase watchlist...")

def start_stream():
    print("Starting TwelveData WebSocket stream...")

def check_news():
    print("Fetching news...")
    return {"latest_news": "Market is active."}
# End of placeholder definitions

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
    # Get the port from environment variables, defaulting to 10000
    port = int(os.environ.get("PORT", 10000))
    
    # 💥 FIX: You must call uvicorn.run() as a function, passing the app object 
    # and configuration arguments, instead of typing a command-line string.
    
    # We pass "main:app" as a string if we need auto-reloading or workers, 
    # but since we are running it directly, passing the app object itself is cleaner 
    # and prevents multiple app initializations when workers are not used.
    # However, to be safe and compatible with the standard "module:app" string, 
    # we'll use that format if we were running outside a simple script.
    
    # For programmatic execution, we use the function call:
    uvicorn.run(
        "main:app",  # The application reference: file_name:app_variable
        host="0.0.0.0",
        port=port,
        log_level="info"
        # Optional: reload=True for development (but costs more resources)
    )
