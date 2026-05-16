"""Tests for RingBuffer."""

from __future__ import annotations

import numpy as np
import pytest


@pytest.fixture
def rb():
    from agent.voice.ring_buffer import RingBuffer

    return RingBuffer(samplerate=16000, duration=1.0)


def test_ring_buffer_initial_empty(rb):
    assert len(rb) == 0
    data = rb.read()
    assert len(data) == 0


def test_ring_buffer_write_and_read(rb):
    chunk = np.ones(4000, dtype=np.float32)
    rb.write(chunk)
    assert len(rb) == 4000
    out = rb.read()
    assert len(out) == 4000
    assert np.allclose(out[:4000], 1.0)


def test_ring_buffer_wraps_around(rb):
    cap = rb.capacity_samples
    first = np.ones(cap - 1000, dtype=np.float32)
    second = np.ones(2000, dtype=np.float32) * 0.5
    rb.write(first)
    rb.write(second)
    assert len(rb) == cap
    out = rb.read()
    assert len(out) == cap
    assert np.allclose(out[: cap - 2000], 1.0)
    assert np.allclose(out[cap - 2000 :], 0.5)


def test_ring_buffer_write_exact_capacity(rb):
    cap = rb.capacity_samples
    data = np.ones(cap, dtype=np.float32)
    rb.write(data)
    assert len(rb) == cap
    out = rb.read()
    assert np.allclose(out, 1.0)


def test_ring_buffer_write_over_capacity(rb):
    data = np.ones(rb.capacity_samples + 1000, dtype=np.float32)
    data[:1000] = 0.5
    data[1000:] = 0.25
    rb.write(data)
    out = rb.read()
    assert len(out) == rb.capacity_samples
    assert np.allclose(out, 0.25)


def test_ring_buffer_clear(rb):
    rb.write(np.ones(4000, dtype=np.float32))
    rb.clear()
    assert len(rb) == 0
    out = rb.read()
    assert len(out) == 0


def test_ring_buffer_write_empty(rb):
    rb.write(np.array([], dtype=np.float32))
    assert len(rb) == 0


def test_ring_buffer_multiple_writes_no_wrap(rb):
    rb.write(np.ones(2000, dtype=np.float32))
    rb.write(np.ones(3000, dtype=np.float32) * 0.5)
    assert len(rb) == 5000
    out = rb.read()
    assert np.allclose(out[:2000], 1.0)
    assert np.allclose(out[2000:5000], 0.5)


def test_ring_buffer_thread_safety(rb):
    import threading

    errors = []

    def writer():
        try:
            for _ in range(100):
                rb.write(np.ones(100, dtype=np.float32))
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(100):
                rb.read()
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
