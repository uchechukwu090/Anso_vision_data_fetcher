"""
WebSocket Server for Real-Time Price Updates
Streams price data from TwelveData to connected frontend clients
"""
import os
import json
import asyncio
import websocket
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from supabase import create_client
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Environment variables
TWELVEDATA_API_KEY = os.getenv("TWELVEDATA_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self.subscribed_symbols: Dict[str, Set[WebSocket]] = {}
        self.twelvedata_ws = None
        self.is_connected = False
        
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"✅ New client connected. Total: {len(self.active_connections)}")
        
    def disconnect(self, websocket: WebSocket):
        """Remove a disconnected client"""
        self.active_connections.discard(websocket)
        # Remove from symbol subscriptions
        for symbol, connections in self.subscribed_symbols.items():
            connections.discard(websocket)
        logger.info(f"❌ Client disconnected. Total: {len(self.active_connections)}")
        
    async def subscribe_symbol(self, websocket: WebSocket, symbol: str):
        """Subscribe a client to a specific symbol"""
        if symbol not in self.subscribed_symbols:
            self.subscribed_symbols[symbol] = set()
        self.subscribed_symbols[symbol].add(websocket)
        logger.info(f"📊 Client subscribed to {symbol}")
        
        # If this is the first subscription for this symbol, subscribe to TwelveData
        if len(self.subscribed_symbols[symbol]) == 1:
            await self.subscribe_to_twelvedata(symbol)
            
    async def unsubscribe_symbol(self, websocket: WebSocket, symbol: str):
        """Unsubscribe a client from a symbol"""
        if symbol in self.subscribed_symbols:
            self.subscribed_symbols[symbol].discard(websocket)
            logger.info(f"📊 Client unsubscribed from {symbol}")
            
            # If no more clients for this symbol, unsubscribe from TwelveData
            if len(self.subscribed_symbols[symbol]) == 0:
                await self.unsubscribe_from_twelvedata(symbol)
                del self.subscribed_symbols[symbol]
    
    async def broadcast_to_symbol(self, symbol: str, data: dict):
        """Broadcast price update to all clients subscribed to a symbol"""
        if symbol in self.subscribed_symbols:
            disconnected = set()
            for connection in self.subscribed_symbols[symbol]:
                try:
                    await connection.send_json(data)
                except Exception as e:
                    logger.error(f"Error sending to client: {e}")
                    disconnected.add(connection)
            
            # Clean up disconnected clients
            for conn in disconnected:
                self.disconnect(conn)
    
    async def connect_to_twelvedata(self):
        """Connect to TwelveData WebSocket"""
        if not TWELVEDATA_API_KEY:
            logger.error("❌ TWELVEDATA_API_KEY not configured")
            return
            
        def on_message(ws, message):
            """Handle incoming messages from TwelveData"""
            try:
                data = json.loads(message)
                if data.get("event") == "price":
                    symbol = data.get("symbol")
                    price = data.get("price")
                    timestamp = data.get("timestamp")
                    
                    # Broadcast to subscribed clients
                    asyncio.run(self.broadcast_to_symbol(symbol, {
                        "type": "price_update",
                        "symbol": symbol,
                        "price": price,
                        "timestamp": timestamp
                    }))
            except Exception as e:
                logger.error(f"Error processing TwelveData message: {e}")
        
        def on_error(ws, error):
            logger.error(f"TwelveData WebSocket error: {error}")
            self.is_connected = False
            
        def on_close(ws, close_status_code, close_msg):
            logger.warning("TwelveData WebSocket closed")
            self.is_connected = False
            
        def on_open(ws):
            logger.info("✅ Connected to TwelveData WebSocket")
            self.is_connected = True
        
        # Create WebSocket connection
        ws_url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={TWELVEDATA_API_KEY}"
        self.twelvedata_ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        )
        
        # Run in separate thread
        import threading
        wst = threading.Thread(target=self.twelvedata_ws.run_forever)
        wst.daemon = True
        wst.start()
        
    async def subscribe_to_twelvedata(self, symbol: str):
        """Subscribe to a symbol on TwelveData"""
        if self.twelvedata_ws and self.is_connected:
            self.twelvedata_ws.send(json.dumps({
                "action": "subscribe",
                "params": {
                    "symbols": symbol
                }
            }))
            logger.info(f"📡 Subscribed to {symbol} on TwelveData")
            
    async def unsubscribe_from_twelvedata(self, symbol: str):
        """Unsubscribe from a symbol on TwelveData"""
        if self.twelvedata_ws and self.is_connected:
            self.twelvedata_ws.send(json.dumps({
                "action": "unsubscribe",
                "params": {
                    "symbols": symbol
                }
            }))
            logger.info(f"📡 Unsubscribed from {symbol} on TwelveData")

# Global connection manager
manager = ConnectionManager()

async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time price updates
    
    Protocol:
    - Client sends: {"action": "subscribe", "symbol": "EUR/USD"}
    - Client sends: {"action": "unsubscribe", "symbol": "EUR/USD"}
    - Server sends: {"type": "price_update", "symbol": "EUR/USD", "price": 1.0850, "timestamp": 1234567890}
    """
    await manager.connect(websocket)
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            action = data.get("action")
            symbol = data.get("symbol")
            
            if action == "subscribe" and symbol:
                await manager.subscribe_symbol(websocket, symbol)
                await websocket.send_json({
                    "type": "subscribed",
                    "symbol": symbol,
                    "status": "success"
                })
                
            elif action == "unsubscribe" and symbol:
                await manager.unsubscribe_symbol(websocket, symbol)
                await websocket.send_json({
                    "type": "unsubscribed",
                    "symbol": symbol,
                    "status": "success"
                })
                
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Initialize TwelveData connection on startup
async def init_websocket():
    """Initialize WebSocket connection to TwelveData"""
    await manager.connect_to_twelvedata()
