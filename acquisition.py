"""EEG data acquisition via BrainFlow.

Wraps BoardShim for Muse 2 (board ID 38) with automatic fallback
to synthetic board (ID -1) when hardware is unavailable.
"""

from __future__ import annotations

import logging

import numpy as np
from brainflow.board_shim import BoardIds, BoardShim, BrainFlowInputParams
from numpy.typing import NDArray

logger = logging.getLogger(__name__)

MUSE_2_BOARD_ID = BoardIds.MUSE_2_BOARD.value  # 38
SYNTHETIC_BOARD_ID = BoardIds.SYNTHETIC_BOARD.value  # -1

MUSE_CHANNEL_NAMES = ("TP9", "AF7", "AF8", "TP10")


class EEGAcquisition:
    """Manages BrainFlow board lifecycle and data retrieval."""

    def __init__(self, synthetic: bool = False) -> None:
        self._force_synthetic = synthetic
        self._board: BoardShim | None = None
        self._board_id: int = SYNTHETIC_BOARD_ID if synthetic else MUSE_2_BOARD_ID
        self._is_synthetic: bool = synthetic
        self._sampling_rate: int = 0
        self._eeg_channels: list[int] = []

    @property
    def is_synthetic(self) -> bool:
        return self._is_synthetic

    @property
    def sampling_rate(self) -> int:
        return self._sampling_rate

    @property
    def board_id(self) -> int:
        return self._board_id

    @property
    def channel_names(self) -> tuple[str, ...]:
        return MUSE_CHANNEL_NAMES

    @property
    def eeg_channels(self) -> list[int]:
        return self._eeg_channels

    def start(self) -> None:
        """Start the BrainFlow session, falling back to synthetic on failure."""
        if self._force_synthetic:
            self._start_board(SYNTHETIC_BOARD_ID)
            return

        try:
            self._start_board(MUSE_2_BOARD_ID)
        except Exception as exc:
            logger.warning("Muse 2 connection failed (%s), falling back to synthetic board", exc)
            self._start_board(SYNTHETIC_BOARD_ID)

    def _start_board(self, board_id: int) -> None:
        params = BrainFlowInputParams()
        if board_id == MUSE_2_BOARD_ID:
            params.board_id = board_id

        self._board_id = board_id
        self._is_synthetic = board_id == SYNTHETIC_BOARD_ID
        self._board = BoardShim(board_id, params)

        self._board.prepare_session()
        self._board.start_stream(45000)  # ring buffer size

        self._sampling_rate = BoardShim.get_sampling_rate(board_id)
        all_eeg = BoardShim.get_eeg_channels(board_id)
        # Muse 2 has 4 EEG channels; synthetic has 16 — take first 4
        self._eeg_channels = all_eeg[:4]

        mode = "synthetic" if self._is_synthetic else "live"
        logger.info(
            "Board started: id=%d, mode=%s, rate=%d Hz, eeg_channels=%s",
            board_id, mode, self._sampling_rate, self._eeg_channels,
        )

    def get_latest_data(self, num_samples: int) -> NDArray[np.float64]:
        """Non-destructive read of the most recent samples from the ring buffer.

        Returns array of shape (num_channels, num_samples) containing all
        board channels. Use `eeg_channels` indices to extract EEG data.
        """
        if self._board is None:
            raise RuntimeError("Board not started")
        return self._board.get_current_board_data(num_samples)

    def stop(self) -> None:
        """Stop streaming and release the board session."""
        if self._board is not None:
            try:
                self._board.stop_stream()
                self._board.release_session()
            except Exception as exc:
                logger.warning("Error stopping board: %s", exc)
            finally:
                self._board = None
            logger.info("Board stopped")
