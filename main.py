import asyncio
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from trading_bot.trader import SolanaTrader
from trading_bot.scanner import TokenScanner

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

trader = SolanaTrader()
scanner = TokenScanner()

@app.get("/")
async def get_index():
    return FileResponse("static/index.html")

@app.get("/api/status")
async def get_status():
    active_positions = {}
    for addr, pos in trader.active_positions.items():
        current_price = await trader.get_token_price(addr)
        active_positions[addr] = {
            **pos,
            'current_price': current_price
        }

    return {
        "metrics": trader.performance_metrics,
        "active_positions": active_positions,
        "position_history": trader.position_history
    }

async def start_bot():
    await scanner.initialize()
    asyncio.create_task(scanner.start_scanning())
    asyncio.create_task(trader.start_trading(scanner))

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_bot())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
