"""WebSocket connection manager and data broadcast loop.

Manages client connections and runs an async broadcast loop that
pushes processed EEG data to all connected clients at a configurable rate.
"""

from __future__ import annotations

import asyncio
import logging
import time

from fastapi import WebSocket

from acquisition import EEGAcquisition
from processing import process_all_channels

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Track active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    @property
    def has_clients(self) -> bool:
        return len(self._connections) > 0

    @property
    def client_count(self) -> int:
        return len(self._connections)

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("Client connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self._connections:
            self._connections.remove(ws)
            logger.info("Client disconnected (%d remaining)", len(self._connections))

    async def broadcast_json(self, data: dict) -> None:
        """Send JSON to all connected clients, removing dead connections."""
        dead: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.disconnect(ws)


async def broadcast_loop(
    acq: EEGAcquisition,
    manager: ConnectionManager,
    update_hz: float = 12.0,
) -> None:
    """Continuously broadcast processed EEG data to connected clients.

    Runs at `update_hz` rate. Skips processing when no clients are connected.
    Uses asyncio.to_thread() for CPU-bound DSP work.
    """
    interval = 1.0 / update_hz
    # Fetch ~4 seconds of data for FFT/band power analysis
    window_seconds = 4.0
    # Only send the latest chunk of raw samples per update for display
    raw_chunk = max(1, int(acq.sampling_rate / update_hz))

    logger.info("Broadcast loop started at %.1f Hz", update_hz)

    while True:
        loop_start = time.monotonic()

        try:
            if manager.has_clients:
                num_samples = int(acq.sampling_rate * window_seconds)
                data = acq.get_latest_data(num_samples)

                if data.shape[1] > 0:
                    result = await asyncio.to_thread(
                        process_all_channels,
                        data,
                        acq.eeg_channels,
                        acq.channel_names,
                        acq.sampling_rate,
                        raw_chunk,
                    )
                    await manager.broadcast_json(result)

        except Exception:
            logger.exception("Error in broadcast loop")

        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, interval - elapsed)
        await asyncio.sleep(sleep_time)
