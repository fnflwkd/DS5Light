"""Isolated stereo duplication candidate with the original length-error contract.

Supported inputs are contiguous byte-oriented buffers: bytes, bytearray, or
contiguous memoryview with one-byte elements. One instance belongs to one audio
thread. This module does not configure capture, block sizes, devices, or timing.
"""

import struct

import numpy as np


class StereoDuplicator:
    """Map int16 [L, R] to [L, R, L, R]; returned bytes own their memory."""

    def __init__(self):
        self.capacity = 0

    def process(self, data):
        if len(data) % 4:
            # Match the original mapper's exception class AND message. This
            # path is reached only for an incomplete stereo int16 frame.
            n = len(data) // 4
            struct.unpack("<" + "h" * (n * 2), data)
        source = np.frombuffer(data, dtype="<i2").reshape(-1, 2)
        n = len(source)
        if not n:
            return b""
        if n > self.capacity:
            self.capacity = max(n, 480)
            self.pcm = np.empty((self.capacity, 4), dtype="<i2")
        output = self.pcm[:n]
        output[:, :2] = source
        output[:, 2:] = source
        return output.tobytes()
