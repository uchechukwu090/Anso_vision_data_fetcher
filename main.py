import os
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import requests

# Import WebSocket server
from websocket_server import websocket_endpoint, init_websocket

app = FastAPI(
    title="Anso Vision Data Fetcher",
    description="Real-time market data aggregation and news service",
    version="2.0.0"
)

# CORS Configuration
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', '*').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Environment variables
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
FINLIGHT_API_KEY = os.getenv("FINLIGHT_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "https://anso-vision-backend.onrender.com")

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    print("🚀 Data Fetcher Service Starting...")
    print(f"📊 Backend URL: {BACKEND_URL}")
    print(f"🔑 TwelveData API: {'Configured' if TWELVEDATA_API_KEY else 'Missing'}")
    print(f"📰 Finlight API: {'Configured' if FINLIGHT_API_KEY else 'Missing'}")
    
    # Initialize WebSocket connection to TwelveData
    await init_websocket()
    print("📡 WebSocket server initialized")

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Anso Vision Data Fetcher",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "candles": "/candles/{symbol}",
            "news": "/news",
            "health": "/health",
            "websocket": "/ws"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Data Fetcher",
        "twelvedata_api": "configured" if TWELVEDATA_API_KEY else "missing",
        "finlight_api": "configured" if FINLIGHT_API_KEY else "missing",
        "websocket": "enabled"
    }

@app.get("/candles/{symbol}")
async def get_candles(
    symbol: str,
    interval: str = "1h",
    outputsize: int = 100
):
    """
    Fetch historical candle data from TwelveData API
    
    This centralizes data fetching and hides the API key from frontend
    """
    if not TWELVEDATA_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="TwelveData API key not configured"
        )
    
    try:
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": outputsize,
            "apikey": TWELVEDATA_API_KEY,
            "format": "JSON"
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if "status" in data and data["status"] == "error":
            raise HTTPException(
                status_code=400,
                detail=data.get("message", "TwelveData API error")
            )
        
        values = data.get("values", [])
        candles = []
        
        for item in values:
            try:
                candles.append({
                    "time": item.get("datetime"),
                    "open": float(item.get("open", 0)),
                    "high": float(item.get("high", 0)),
                    "low": float(item.get("low", 0)),
                    "close": float(item.get("close", 0)),
                    "volume": float(item.get("volume", 0))
                })
            except (ValueError, TypeError) as e:
                print(f"⚠️ Skipping invalid candle: {e}")
                continue
        
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "candles": candles,
            "count": len(candles)
        }
    
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504,
            detail="TwelveData API timeout"
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch data from TwelveData: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )

@app.get("/news")
async def get_news():
    """
    Fetch high-impact economic news from Finlight API
    """
    if not FINLIGHT_API_KEY:
        return {
            "success": False,
            "error": "Finlight API key not configured",
            "impactful_events": []
        }
    
    try:
        headers = {"Authorization": f"Bearer {FINLIGHT_API_KEY}"}
        response = requests.get(
            "https://api.finlight.ai/calendar/today",
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": "Failed to fetch news",
                "status": response.status_code,
                "impactful_events": []
            }
        
        data = response.json()
        events = data.get("events", [])
        
        impactful_events = [
            event for event in events 
            if event.get("impact") == "high"
        ]
        
        return {
            "success": True,
            "impactful_events": impactful_events,
            "total_events": len(events),
            "high_impact_count": len(impactful_events)
        }
    
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "Finlight API timeout",
            "impactful_events": []
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "impactful_events": []
        }

@app.websocket("/ws")
async def websocket_route(websocket: WebSocket):
    """
    WebSocket endpoint for real-time price updates
    
    Usage:
    1. Connect to: wss://anso-vision-data-fetcher.onrender.com/ws
    2. Send: {"action": "subscribe", "symbol": "EUR/USD"}
    3. Receive: {"type": "price_update", "symbol": "EUR/USD", "price": 1.0850, "timestamp": 1234567890}
    """
    await websocket_endpoint(websocket)

@app.get("/start")
async def start_fetcher():
    """Manual trigger to restart services"""
    return {
        "status": "noted",
        "message": "WebSocket streaming is enabled"
    }

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    
    print(f"🚀 Starting Data Fetcher Service on port {port}")
    print(f"🔒 CORS Origins: {ALLOWED_ORIGINS}")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False
    )
