"""Stateless DSP functions for EEG signal processing.

Uses BrainFlow's DataFilter for FFT, band power extraction, and
signal quality estimation. All functions are pure and operate on
numpy arrays.
"""

from __future__ import annotations

import time

import numpy as np
from brainflow.data_filter import DataFilter
from numpy.typing import NDArray

# Frequency bands (Hz)
BANDS = {
    "delta": (0.5, 4.0),
    "theta": (4.0, 8.0),
    "alpha": (8.0, 13.0),
    "beta": (13.0, 30.0),
    "gamma": (30.0, 50.0),
}

# Signal quality thresholds
_RMS_MIN = 0.5   # µV — below this, likely flatline
_RMS_MAX = 200.0  # µV — above this, likely artifact
_LINE_NOISE_RATIO_MAX = 0.4  # 50/60 Hz power as fraction of total


def compute_fft(
    channel_data: NDArray[np.float64],
    sampling_rate: int,
    max_freq: float = 60.0,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Compute PSD using Welch's method via BrainFlow.

    Returns (freqs, psd) arrays truncated to max_freq.
    """
    nfft = _largest_power_of_2(len(channel_data))
    if nfft < 64:
        return np.array([]), np.array([])

    psd = DataFilter.get_psd_welch(
        channel_data,
        nfft=nfft,
        overlap=nfft // 2,
        sampling_rate=sampling_rate,
        window=2,  # Hamming
    )
    # psd is a 2D array: [amplitudes, frequencies]
    amplitudes = psd[0]
    freqs = psd[1]

    # Truncate to max_freq
    mask = freqs <= max_freq
    return freqs[mask], amplitudes[mask]


def compute_band_powers(
    channel_data: NDArray[np.float64],
    sampling_rate: int,
) -> dict[str, float]:
    """Extract power in standard EEG frequency bands."""
    nfft = _largest_power_of_2(len(channel_data))
    if nfft < 64:
        return {b: 0.0 for b in BANDS}

    psd = DataFilter.get_psd_welch(
        channel_data,
        nfft=nfft,
        overlap=nfft // 2,
        sampling_rate=sampling_rate,
        window=2,
    )

    powers: dict[str, float] = {}
    for band_name, (low, high) in BANDS.items():
        try:
            power = DataFilter.get_band_power(psd, low, high)
            powers[band_name] = float(power)
        except Exception:
            powers[band_name] = 0.0

    return powers


def compute_signal_quality(
    channel_data: NDArray[np.float64],
    sampling_rate: int,
) -> float:
    """Heuristic signal quality score from 0.0 (bad) to 1.0 (good).

    Checks for:
    - RMS amplitude in expected range
    - Flatline detection (very low variance)
    - Line noise contamination (50/60 Hz)
    """
    if len(channel_data) < 64:
        return 0.0

    score = 1.0

    # RMS check
    rms = float(np.sqrt(np.mean(channel_data**2)))
    if rms < _RMS_MIN:
        score *= 0.2  # likely flatline
    elif rms > _RMS_MAX:
        score *= 0.3  # likely artifact

    # Flatline: standard deviation near zero
    std = float(np.std(channel_data))
    if std < 0.1:
        score *= 0.1

    # Line noise check (50/60 Hz band vs total)
    try:
        nfft = _largest_power_of_2(len(channel_data))
        psd = DataFilter.get_psd_welch(
            channel_data, nfft=nfft, overlap=nfft // 2,
            sampling_rate=sampling_rate, window=2,
        )
        total_power = float(np.sum(psd[0]))
        if total_power > 0:
            noise_power_50 = float(DataFilter.get_band_power(psd, 48.0, 52.0))
            noise_power_60 = float(DataFilter.get_band_power(psd, 58.0, 62.0))
            noise_ratio = (noise_power_50 + noise_power_60) / total_power
            if noise_ratio > _LINE_NOISE_RATIO_MAX:
                score *= 0.5
    except Exception:
        pass

    return max(0.0, min(1.0, score))


def process_all_channels(
    data: NDArray[np.float64],
    eeg_channels: list[int],
    channel_names: tuple[str, ...],
    sampling_rate: int,
    raw_tail: int = 0,
) -> dict:
    """Process all EEG channels and return a JSON-serializable dict.

    Args:
        data: Full board data array (all channels x samples).
        eeg_channels: Indices of EEG channels in the data array.
        channel_names: Human-readable names for each EEG channel.
        sampling_rate: Board sampling rate in Hz.
        raw_tail: Number of most-recent raw samples to include.
            0 means send all samples.
    """
    result: dict = {
        "timestamp": time.time(),
        "raw": {},
        "fft": {"freqs": []},
        "band_powers": {},
        "signal_quality": {},
    }

    num_samples = data.shape[1] if data.ndim == 2 else 0
    if num_samples < 64:
        # Not enough data yet — return empty structure
        for name in channel_names:
            result["raw"][name] = []
            result["fft"][name] = []
            result["band_powers"][name] = {b: 0.0 for b in BANDS}
            result["signal_quality"][name] = 0.0
        return result

    freqs_set = False

    for ch_idx, name in zip(eeg_channels, channel_names):
        if ch_idx >= data.shape[0]:
            continue

        channel_data = data[ch_idx].copy()

        # Raw waveform — send only the tail for incremental display
        if raw_tail > 0 and len(channel_data) > raw_tail:
            result["raw"][name] = channel_data[-raw_tail:].tolist()
        else:
            result["raw"][name] = channel_data.tolist()

        # FFT
        freqs, psd_values = compute_fft(channel_data, sampling_rate)
        if not freqs_set:
            result["fft"]["freqs"] = freqs.tolist()
            freqs_set = True
        result["fft"][name] = psd_values.tolist()

        # Band powers
        result["band_powers"][name] = compute_band_powers(channel_data, sampling_rate)

        # Signal quality
        result["signal_quality"][name] = compute_signal_quality(channel_data, sampling_rate)

    return result


def _largest_power_of_2(n: int) -> int:
    """Return the largest power of 2 <= n."""
    if n <= 0:
        return 0
    p = 1
    while p * 2 <= n:
        p <<= 1
    return p
