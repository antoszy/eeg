# Muse 2 EEG Dashboard

Real-time EEG visualization dashboard for the [Muse 2](https://choosemuse.com/) headband. Streams raw brainwaves, power spectral density, frequency band powers, and signal quality to a browser-based UI over WebSocket.

![Stack](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![BrainFlow](https://img.shields.io/badge/BrainFlow-5.x-blue)
![Plotly](https://img.shields.io/badge/Plotly.js-3F4F75?style=flat&logo=plotly&logoColor=white)

## Features

- **4-channel raw EEG** — TP9, AF7, AF8, TP10 at 256 Hz (live) / 250 Hz (synthetic)
- **Power spectral density** — Welch's method, 0–60 Hz, log scale
- **Band powers** — delta, theta, alpha, beta, gamma per channel
- **Signal quality** — real-time contact quality indicators (green/yellow/red)
- **Auto-fallback** — connects to Muse 2 hardware, falls back to synthetic board if unavailable
- **WebSocket streaming** — 12 Hz updates, ~15 KB/msg, auto-reconnect
- **Dark theme** — single-page UI, no build step, Plotly.js via CDN

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run with synthetic data (no hardware needed)
./start.sh --synthetic

# Run with Muse 2
./start.sh
```

The dashboard opens at [http://localhost:8080](http://localhost:8080).

## Usage

### One-shot launcher

```bash
./start.sh              # Connect Muse 2 → start server → open browser
./start.sh --synthetic  # Skip Bluetooth, use synthetic board
```

Press `Ctrl+C` to stop.

### Manual

```bash
# Optional: pair Muse via Bluetooth first
./connect-muse.sh

# Start server
python main.py                          # auto-detect Muse 2
python main.py --synthetic              # force synthetic
python main.py --host 0.0.0.0 --port 9090 --update-hz 15
```

## System Requirements

- Python 3.10+
- Bluetooth adapter (for live Muse 2)
- Linux BLE dependencies:
  ```bash
  sudo apt-get install libdbus-1-dev libbluetooth-dev
  ```

## Architecture

```
Muse 2 (BLE) → BrainFlow ring buffer (256 Hz)
  → broadcast_loop (asyncio, 12 Hz) → process_all_channels()
    → WebSocket JSON → Browser → Plotly.react()
```

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app, CLI args, lifespan, routes |
| `acquisition.py` | BrainFlow board lifecycle, Muse 2 / synthetic fallback |
| `processing.py` | FFT (Welch PSD), band powers, signal quality |
| `server.py` | WebSocket connection manager, 12 Hz broadcast loop |
| `static/` | Single-page dashboard (HTML + CSS + JS) |
| `start.sh` | One-shot launcher (connect + serve + open browser) |
| `connect-muse.sh` | Bluetooth pairing helper |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Dashboard UI |
| `GET /api/info` | Board metadata (sampling rate, mode, channels) |
| `WS /ws` | Real-time EEG data stream |

### WebSocket payload

```json
{
  "timestamp": 1234567890.123,
  "raw": {"TP9": [...], "AF7": [...], "AF8": [...], "TP10": [...]},
  "fft": {"freqs": [...], "TP9": [...], ...},
  "band_powers": {"TP9": {"delta": 0.3, "theta": 0.2, "alpha": 0.5, "beta": 0.1, "gamma": 0.05}, ...},
  "signal_quality": {"TP9": 0.85, "AF7": 0.92, ...}
}
```

## License

MIT
