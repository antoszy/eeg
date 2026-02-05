/**
 * Muse 2 EEG Dashboard — WebSocket client and Plotly chart manager.
 *
 * Connects to the backend WebSocket, receives processed EEG data,
 * and updates Plotly charts at ~12 FPS.
 */

const CHANNEL_NAMES = ["TP9", "AF7", "AF8", "TP10"];
const CHANNEL_COLORS = ["#58a6ff", "#f0883e", "#3fb950", "#bc8cff"];
const BAND_NAMES = ["delta", "theta", "alpha", "beta", "gamma"];
const BAND_COLORS = ["#8b5cf6", "#58a6ff", "#3fb950", "#f0883e", "#f85149"];

const PLOTLY_BG = "#1c2128";
const PLOTLY_GRID = "#30363d";
const PLOTLY_TEXT = "#8b949e";

// Rolling raw buffer — keep ~4 seconds of data
const RAW_BUFFER_MAX = 1024;

const rawBuffers = {};
CHANNEL_NAMES.forEach(ch => { rawBuffers[ch] = []; });

let ws = null;
let chartsInitialized = false;
let reconnectTimeout = null;

// ── Chart initialization ─────────────────────────────────────────────

function initCharts() {
    initRawChart();
    initFFTChart();
    initBandChart();
    chartsInitialized = true;
}

function plotlyLayout(overrides = {}) {
    return Object.assign({
        paper_bgcolor: PLOTLY_BG,
        plot_bgcolor: PLOTLY_BG,
        font: { color: PLOTLY_TEXT, size: 11 },
        margin: { l: 55, r: 20, t: 35, b: 40 },
        legend: {
            orientation: "h",
            x: 0.5,
            xanchor: "center",
            y: 1.12,
            font: { size: 11 },
        },
        xaxis: { gridcolor: PLOTLY_GRID, zeroline: false },
        yaxis: { gridcolor: PLOTLY_GRID, zeroline: false },
    }, overrides);
}

function initRawChart() {
    const traces = CHANNEL_NAMES.map((ch, i) => ({
        y: [],
        type: "scattergl",
        mode: "lines",
        name: ch,
        line: { color: CHANNEL_COLORS[i], width: 1 },
        yaxis: i === 0 ? "y" : `y${i + 1}`,
    }));

    const yAxes = {};
    const domainGap = 0.03;
    const domainSize = (1 - domainGap * 3) / 4;

    CHANNEL_NAMES.forEach((ch, i) => {
        const key = i === 0 ? "yaxis" : `yaxis${i + 1}`;
        const bottom = i * (domainSize + domainGap);
        yAxes[key] = {
            domain: [bottom, bottom + domainSize],
            gridcolor: PLOTLY_GRID,
            zeroline: false,
            title: { text: ch, font: { size: 10 } },
            showticklabels: true,
            tickfont: { size: 9 },
        };
    });

    const layout = plotlyLayout({
        title: { text: "Raw EEG", font: { size: 14 } },
        xaxis: {
            gridcolor: PLOTLY_GRID,
            zeroline: false,
            title: { text: "Samples", font: { size: 10 } },
        },
        showlegend: false,
        ...yAxes,
        height: 420,
    });

    Plotly.newPlot("raw-chart", traces, layout, { responsive: true, displayModeBar: false });
}

function initFFTChart() {
    const traces = CHANNEL_NAMES.map((ch, i) => ({
        x: [],
        y: [],
        type: "scattergl",
        mode: "lines",
        name: ch,
        line: { color: CHANNEL_COLORS[i], width: 1.5 },
    }));

    const layout = plotlyLayout({
        title: { text: "Power Spectral Density", font: { size: 14 } },
        xaxis: {
            gridcolor: PLOTLY_GRID,
            zeroline: false,
            title: { text: "Frequency (Hz)", font: { size: 10 } },
            range: [0, 60],
        },
        yaxis: {
            gridcolor: PLOTLY_GRID,
            zeroline: false,
            title: { text: "Power (µV²/Hz)", font: { size: 10 } },
            type: "log",
        },
        height: 340,
    });

    Plotly.newPlot("fft-chart", traces, layout, { responsive: true, displayModeBar: false });
}

function initBandChart() {
    const traces = CHANNEL_NAMES.map((ch, i) => ({
        x: BAND_NAMES,
        y: BAND_NAMES.map(() => 0),
        type: "bar",
        name: ch,
        marker: { color: CHANNEL_COLORS[i] },
    }));

    const layout = plotlyLayout({
        title: { text: "Band Powers", font: { size: 14 } },
        barmode: "group",
        xaxis: {
            gridcolor: PLOTLY_GRID,
            zeroline: false,
        },
        yaxis: {
            gridcolor: PLOTLY_GRID,
            zeroline: false,
            title: { text: "Power (µV²)", font: { size: 10 } },
        },
        height: 340,
    });

    Plotly.newPlot("band-chart", traces, layout, { responsive: true, displayModeBar: false });
}

// ── Chart updates ────────────────────────────────────────────────────

function updateCharts(data) {
    updateRawChart(data.raw);
    updateFFTChart(data.fft);
    updateBandChart(data.band_powers);
    updateSignalQuality(data.signal_quality);
}

function updateRawChart(raw) {
    const update = { y: [] };

    CHANNEL_NAMES.forEach(ch => {
        const incoming = raw[ch] || [];
        const buf = rawBuffers[ch];
        buf.push(...incoming);
        if (buf.length > RAW_BUFFER_MAX) {
            buf.splice(0, buf.length - RAW_BUFFER_MAX);
        }
        update.y.push(buf.slice());
    });

    Plotly.react(
        "raw-chart",
        CHANNEL_NAMES.map((ch, i) => ({
            y: update.y[i],
            type: "scattergl",
            mode: "lines",
            name: ch,
            line: { color: CHANNEL_COLORS[i], width: 1 },
            yaxis: i === 0 ? "y" : `y${i + 1}`,
        })),
        document.getElementById("raw-chart").layout
    );
}

function updateFFTChart(fft) {
    const freqs = fft.freqs || [];

    Plotly.react(
        "fft-chart",
        CHANNEL_NAMES.map((ch, i) => ({
            x: freqs,
            y: fft[ch] || [],
            type: "scattergl",
            mode: "lines",
            name: ch,
            line: { color: CHANNEL_COLORS[i], width: 1.5 },
        })),
        document.getElementById("fft-chart").layout
    );
}

function updateBandChart(bandPowers) {
    Plotly.react(
        "band-chart",
        CHANNEL_NAMES.map((ch, i) => ({
            x: BAND_NAMES,
            y: BAND_NAMES.map(b => (bandPowers[ch] || {})[b] || 0),
            type: "bar",
            name: ch,
            marker: { color: CHANNEL_COLORS[i] },
        })),
        document.getElementById("band-chart").layout
    );
}

function updateSignalQuality(quality) {
    CHANNEL_NAMES.forEach(ch => {
        const dot = document.getElementById(`quality-${ch}`);
        if (!dot) return;

        const score = quality[ch] || 0;
        dot.classList.remove("good", "fair", "poor");

        if (score >= 0.7) {
            dot.classList.add("good");
        } else if (score >= 0.4) {
            dot.classList.add("fair");
        } else {
            dot.classList.add("poor");
        }

        dot.title = `${ch}: ${(score * 100).toFixed(0)}%`;
    });
}

// ── Board info ───────────────────────────────────────────────────────

async function fetchBoardInfo() {
    try {
        const resp = await fetch("/api/info");
        const info = await resp.json();
        const badge = document.getElementById("mode-badge");

        if (info.is_synthetic) {
            badge.textContent = "Synthetic";
            badge.className = "badge badge-synthetic";
        } else {
            badge.textContent = "Live";
            badge.className = "badge badge-live";
        }
    } catch {
        // Will retry on reconnect
    }
}

// ── WebSocket ────────────────────────────────────────────────────────

function connect() {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        console.log("WebSocket connected");
        const statusDot = document.getElementById("connection-status");
        statusDot.classList.remove("disconnected");
        statusDot.classList.add("connected");
        statusDot.title = "Connected";
        fetchBoardInfo();
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (!chartsInitialized) {
            initCharts();
        }
        updateCharts(data);
    };

    ws.onclose = () => {
        console.log("WebSocket disconnected, reconnecting in 2s...");
        const statusDot = document.getElementById("connection-status");
        statusDot.classList.remove("connected");
        statusDot.classList.add("disconnected");
        statusDot.title = "Disconnected";
        scheduleReconnect();
    };

    ws.onerror = () => {
        ws.close();
    };
}

function scheduleReconnect() {
    if (reconnectTimeout) clearTimeout(reconnectTimeout);
    reconnectTimeout = setTimeout(connect, 2000);
}

// ── Bootstrap ────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    connect();
});
