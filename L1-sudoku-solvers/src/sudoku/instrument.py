"""Lightweight instrumentation: node counting and peak-memory measurement."""

from __future__ import annotations

import time
import tracemalloc
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass
class Measurement:
    """Captured timing and peak-memory of an instrumented block."""

    elapsed_s: float = 0.0
    peak_mem_bytes: int = 0


@contextmanager
def measure(track_memory: bool = True) -> Iterator[Measurement]:
    """Context manager measuring wall-clock time and peak memory of a block.

    Memory tracking uses :mod:`tracemalloc`. It is reasonably cheap but adds
    overhead, so it can be disabled for the most timing-sensitive runs.
    """
    m = Measurement()
    started_tm = False
    if track_memory and not tracemalloc.is_tracing():
        tracemalloc.start()
        started_tm = True
    start = time.perf_counter()
    try:
        yield m
    finally:
        m.elapsed_s = time.perf_counter() - start
        if track_memory:
            _, peak = tracemalloc.get_traced_memory()
            m.peak_mem_bytes = peak
            if started_tm:
                tracemalloc.stop()
