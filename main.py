import os
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import requests
import logging
import asyncio
import json
from typing import Set, Dict
import websocket as ws_client
import threading

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Anso Vision Data Fetcher",
    description="Real-time market data aggregation and news service",
    version="2.0.0"
)

# CORS Configuration - ALLOW ALL ORIGINS (for now)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# Environment variables
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
FINLIGHT_API_KEY = os.getenv("FINLIGHT_API_KEY")
BACKEND_URL = os.getenv("BACKEND_URL", "https://anso-vision-backend.onrender.com")

# WebSocket connection manager
class WebSocketManager:
    def __init__(self):
        self.frontend_connections: Set[WebSocket] = set()
        self.twelvedata_ws = None
        self.is_connected = False
        self.subscribed_symbols: Set[str] = set()
        self.latest_prices: Dict[str, dict] = {}
        self.candle_aggregators: Dict[str, 'CandleAggregator'] = {}  # symbol -> aggregator
        
    async def connect_frontend(self, websocket: WebSocket):
        """Accept frontend WebSocket connection"""
        await websocket.accept()
        self.frontend_connections.add(websocket)
        logger.info(f"✅ Frontend client connected. Total: {len(self.frontend_connections)}")
        
        # Send current prices
        if self.latest_prices:
            try:
                await websocket.send_json({
                    "type": "initial_prices",
                    "prices": self.latest_prices
                })
            except:
                pass
    
    def disconnect_frontend(self, websocket: WebSocket):
        """Remove disconnected frontend client"""
        self.frontend_connections.discard(websocket)
        logger.info(f"❌ Frontend client disconnected. Total: {len(self.frontend_connections)}")
    
    async def broadcast_price(self, symbol: str, price: float, timestamp: int):
        """Broadcast price update to all connected frontend clients"""
        self.latest_prices[symbol] = {
            "price": price,
            "timestamp": timestamp
        }
        
        message = {
            "type": "price_update",
            "symbol": symbol,
            "price": price,
            "timestamp": timestamp
        }
        
        disconnected = set()
        for connection in self.frontend_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending to frontend client: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect_frontend(conn)
    
    def on_twelvedata_message(self, ws, message):
        """Handle messages from TwelveData WebSocket"""
        try:
            data = json.loads(message)
            
            if data.get("event") == "price":
                symbol = data.get("symbol")
                price = float(data.get("price", 0))
                timestamp = int(data.get("timestamp", 0))
                
                # Initialize aggregator if needed
                if symbol not in self.candle_aggregators:
                    from candle_aggregator import CandleAggregator
                    self.candle_aggregators[symbol] = CandleAggregator(timeframe_minutes=60)
                    self.candle_aggregators[symbol].on_candle_complete = self.on_candle_complete
                
                # Process tick into candle
                self.candle_aggregators[symbol].process_tick(symbol, price, timestamp)
                
                # Broadcast to frontend clients (run in event loop)
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_price(symbol, price, timestamp),
                    asyncio.get_event_loop()
                )
                
            elif data.get("event") == "subscribe-status":
                logger.info(f"TwelveData subscription status: {data}")
                
        except Exception as e:
            logger.error(f"Error processing TwelveData message: {e}")
    
    async def on_candle_complete(self, symbol: str, candles: list):
        """Called when a new candle completes"""
        logger.info(f"🕯️ Candle completed for {symbol}, triggering analysis...")
        
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{BACKEND_URL}/api/candle-complete",
                    json={
                        "symbol": symbol,
                        "candles": candles
                    }
                )
                
                if response.status_code == 200:
                    logger.info(f"✅ Analysis triggered for {symbol}")
                else:
                    logger.warning(f"⚠️ Backend returned {response.status_code}")
        
        except Exception as e:
            logger.error(f"❌ Failed to trigger analysis: {e}")
    
    def on_twelvedata_error(self, ws, error):
        logger.error(f"TwelveData WebSocket error: {error}")
        self.is_connected = False
    
    def on_twelvedata_close(self, ws, close_status_code, close_msg):
        logger.warning(f"TwelveData WebSocket closed: {close_status_code} - {close_msg}")
        self.is_connected = False
        
        # Attempt to reconnect after 5 seconds
        threading.Timer(5.0, self.connect_to_twelvedata).start()
    
    def on_twelvedata_open(self, ws):
        logger.info("✅ Connected to TwelveData WebSocket")
        self.is_connected = True
        
        # Subscribe to all symbols (only when explicitly requested)
        # Auto-subscription disabled - symbols must be subscribed via /ws endpoint
        # if self.subscribed_symbols:
        #     self.subscribe_symbols(list(self.subscribed_symbols))
    
    def connect_to_twelvedata(self):
        """Connect to TwelveData WebSocket"""
        if not TWELVEDATA_API_KEY:
            logger.error("❌ TWELVEDATA_API_KEY not configured")
            return
        
        ws_url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={TWELVEDATA_API_KEY}"
        
        self.twelvedata_ws = ws_client.WebSocketApp(
            ws_url,
            on_open=self.on_twelvedata_open,
            on_message=self.on_twelvedata_message,
            on_error=self.on_twelvedata_error,
            on_close=self.on_twelvedata_close
        )
        
        # Run in separate thread
        wst = threading.Thread(target=self.twelvedata_ws.run_forever)
        wst.daemon = True
        wst.start()
        
        logger.info("📡 TwelveData WebSocket thread started")
    
    def subscribe_symbols(self, symbols: list):
        """Subscribe to symbols on TwelveData"""
        if not self.twelvedata_ws or not self.is_connected:
            logger.warning("Cannot subscribe - TwelveData WebSocket not connected")
            return
        
        try:
            message = {
                "action": "subscribe",
                "params": {
                    "symbols": ",".join(symbols)
                }
            }
            self.twelvedata_ws.send(json.dumps(message))
            logger.info(f"📡 Subscribed to: {symbols}")
            
            for symbol in symbols:
                self.subscribed_symbols.add(symbol)
                
        except Exception as e:
            logger.error(f"Error subscribing to symbols: {e}")
    
    def unsubscribe_symbols(self, symbols: list):
        """Unsubscribe from symbols on TwelveData"""
        if not self.twelvedata_ws or not self.is_connected:
            return
        
        try:
            message = {
                "action": "unsubscribe",
                "params": {
                    "symbols": ",".join(symbols)
                }
            }
            self.twelvedata_ws.send(json.dumps(message))
            logger.info(f"📡 Unsubscribed from: {symbols}")
            
            for symbol in symbols:
                self.subscribed_symbols.discard(symbol)
                
        except Exception as e:
            logger.error(f"Error unsubscribing from symbols: {e}")

# Global WebSocket manager
ws_manager = WebSocketManager()

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("🚀 Data Fetcher Service Starting...")
    logger.info(f"📊 Backend URL: {BACKEND_URL}")
    logger.info(f"🔑 TwelveData API: {'Configured' if TWELVEDATA_API_KEY else 'Missing'}")
    logger.info(f"📰 Finlight API: {'Configured' if FINLIGHT_API_KEY else 'Missing'}")
    logger.info(f"🌐 CORS: Allowing ALL origins")
    
    # Connect to TwelveData WebSocket
    ws_manager.connect_to_twelvedata()

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Anso Vision Data Fetcher",
        "version": "2.0.0",
        "status": "running",
        "cors": "enabled (all origins)",
        "websocket_status": "connected" if ws_manager.is_connected else "disconnected",
        "subscribed_symbols": list(ws_manager.subscribed_symbols),
        "endpoints": {
            "candles": "/candles/{symbol} - Get historical OHLC for analysis",
            "news": "/news - Get high-impact news",
            "health": "/health - Health check",
            "websocket": "/ws - Real-time price streaming"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Data Fetcher",
        "cors": "enabled",
        "twelvedata_api": "configured" if TWELVEDATA_API_KEY else "missing",
        "finlight_api": "configured" if FINLIGHT_API_KEY else "missing",
        "websocket_connected": ws_manager.is_connected,
        "subscribed_symbols": list(ws_manager.subscribed_symbols),
        "frontend_clients": len(ws_manager.frontend_connections)
    }

@app.get("/candles/{symbol:path}")
async def get_candles(
    symbol: str,
    interval: str = "1h",
    outputsize: int = 250
):
    """
    Fetch historical OHLC candle data from TwelveData REST API
    """
    logger.info(f"📊 Fetching candles for {symbol}, interval: {interval}")
    
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
            logger.error(f"TwelveData API error: {data.get('message')}")
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
                logger.warning(f"⚠️ Skipping invalid candle: {e}")
                continue
        
        logger.info(f"✅ Successfully fetched {len(candles)} candles for {symbol}")
        
        return {
            "success": True,
            "symbol": symbol,
            "interval": interval,
            "candles": candles,
            "count": len(candles)
        }
    
    except requests.exceptions.Timeout:
        logger.error("TwelveData API timeout")
        raise HTTPException(
            status_code=504,
            detail="TwelveData API timeout"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"TwelveData request failed: {str(e)}")
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch data from TwelveData: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Internal error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )

@app.get("/news")
async def get_news():
    """Fetch high-impact economic news from Finlight API"""
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
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for REAL-TIME price streaming"""
    await ws_manager.connect_frontend(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            action = data.get("action")
            symbols = data.get("symbols", [])
            
            if action == "subscribe" and symbols:
                ws_manager.subscribe_symbols(symbols)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbols": symbols,
                    "status": "success"
                })
                
            elif action == "unsubscribe" and symbols:
                ws_manager.unsubscribe_symbols(symbols)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbols": symbols,
                    "status": "success"
                })
                
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        ws_manager.disconnect_frontend(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect_frontend(websocket)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    
    logger.info(f"🚀 Starting Data Fetcher Service on port {port}")
    logger.info(f"🌐 CORS: Allowing ALL origins")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        reload=False
    )
