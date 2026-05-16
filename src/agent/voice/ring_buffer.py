from __future__ import annotations

import threading

import numpy as np


class RingBuffer:
    """Thread-safe circular buffer for continuous PCM audio.

    Stores ``float32`` mono audio at a fixed capacity in seconds.
    Written chunks silently evict older samples when capacity is exceeded.
    """

    def __init__(self, samplerate: int, duration: float) -> None:
        self._capacity = int(samplerate * duration)
        self._buffer = np.zeros(self._capacity, dtype=np.float32)
        self._pos = 0
        self._lock = threading.Lock()
        self._full = False

    @property
    def capacity_samples(self) -> int:
        return self._capacity

    def write(self, data: np.ndarray) -> None:
        n = len(data)
        if n == 0:
            return
        with self._lock:
            if n >= self._capacity:
                self._buffer[:] = data[-self._capacity :]
                self._pos = 0
                self._full = True
                return
            space = self._capacity - self._pos
            if n <= space:
                self._buffer[self._pos : self._pos + n] = data
            else:
                self._buffer[self._pos :] = data[:space]
                self._buffer[: n - space] = data[space:]
            self._pos = (self._pos + n) % self._capacity
            if self._pos == 0 or not self._full and self._pos + n >= self._capacity:
                self._full = True

    def read(self) -> np.ndarray:
        with self._lock:
            if not self._full and self._pos == 0:
                return np.array([], dtype=np.float32)
            if self._full:
                return np.concatenate([self._buffer[self._pos :], self._buffer[: self._pos]])
            return self._buffer[: self._pos].copy()

    def clear(self) -> None:
        with self._lock:
            self._buffer.fill(0.0)
            self._pos = 0
            self._full = False

    def __len__(self) -> int:
        with self._lock:
            if self._full:
                return self._capacity
            return self._pos
