"""Muse 2 EEG Dashboard — FastAPI application entry point.

Usage:
    python main.py                     # Try Muse 2, fallback to synthetic
    python main.py --synthetic         # Force synthetic board
    python main.py --host 0.0.0.0 --port 8080 --update-hz 15
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from acquisition import EEGAcquisition
from server import ConnectionManager, broadcast_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global state — initialized during lifespan
acq: EEGAcquisition
manager: ConnectionManager
_broadcast_task: asyncio.Task  # type: ignore[type-arg]
_cli_args: argparse.Namespace


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Muse 2 EEG Dashboard")
    parser.add_argument("--synthetic", action="store_true", help="Force synthetic board")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--update-hz", type=float, default=12.0, help="WebSocket update rate (default: 12)")
    return parser.parse_args()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage BrainFlow session and broadcast task lifecycle."""
    global acq, manager, _broadcast_task

    acq = EEGAcquisition(synthetic=_cli_args.synthetic)
    manager = ConnectionManager()

    acq.start()
    _broadcast_task = asyncio.create_task(
        broadcast_loop(acq, manager, update_hz=_cli_args.update_hz)
    )

    logger.info(
        "Dashboard ready at http://%s:%d (mode: %s)",
        _cli_args.host, _cli_args.port,
        "synthetic" if acq.is_synthetic else "live",
    )

    yield

    _broadcast_task.cancel()
    try:
        await _broadcast_task
    except asyncio.CancelledError:
        pass
    acq.stop()


app = FastAPI(title="Muse 2 EEG Dashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def dashboard() -> FileResponse:
    return FileResponse("static/index.html")


@app.get("/api/info")
async def board_info() -> JSONResponse:
    return JSONResponse({
        "board_id": acq.board_id,
        "sampling_rate": acq.sampling_rate,
        "channel_names": list(acq.channel_names),
        "eeg_channels": acq.eeg_channels,
        "is_synthetic": acq.is_synthetic,
        "clients_connected": manager.client_count,
    })


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; client doesn't send data
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


if __name__ == "__main__":
    import uvicorn

    _cli_args = parse_args()
    uvicorn.run(
        app,
        host=_cli_args.host,
        port=_cli_args.port,
        log_level="info",
    )
