"""Stream long clinical recordings directly to disk."""

from __future__ import annotations

import queue
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd


class StreamingDiskRecorder:
    """Writes 16-bit PCM WAV via a background writer — safe for multi-hour sessions."""

    def __init__(
        self,
        wav_path: Path,
        sample_rate: int = 16000,
        channels: int = 1,
        max_duration_sec: float = 7200,
    ):
        self.wav_path = wav_path
        self.sample_rate = sample_rate
        self.channels = channels
        self.max_duration_sec = max_duration_sec
        self._wf: wave.Wave_write | None = None
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._queue: queue.SimpleQueue[bytes | None] = queue.SimpleQueue()
        self._writer_thread: threading.Thread | None = None
        self._started_at: float | None = None

    @property
    def elapsed_seconds(self) -> float:
        if self._started_at is None:
            return 0.0
        return time.time() - self._started_at

    @property
    def is_recording(self) -> bool:
        return self._recording

    def is_over_limit(self) -> bool:
        return self.elapsed_seconds >= self.max_duration_sec

    def _callback(self, indata, frames, time_info, status):
        if status:
            print(f"Clinical audio status: {status}", file=sys.stderr)
        if not self._recording:
            return
        flat = indata.flatten()
        audio_int16 = (np.clip(flat, -1.0, 1.0) * 32767).astype(np.int16)
        self._queue.put(audio_int16.tobytes())

    def _writer_loop(self):
        while True:
            try:
                chunk = self._queue.get(timeout=0.25)
            except queue.Empty:
                if not self._recording:
                    break
                continue
            if chunk is None:
                break
            if self._wf is not None:
                self._wf.writeframes(chunk)

    def start(self) -> None:
        self.wav_path.parent.mkdir(parents=True, exist_ok=True)
        self._wf = wave.open(str(self.wav_path), "wb")
        self._wf.setnchannels(self.channels)
        self._wf.setsampwidth(2)
        self._wf.setframerate(self.sample_rate)
        self._recording = True
        self._started_at = time.time()
        self._writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer_thread.start()
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._callback,
            blocksize=2048,
        )
        self._stream.start()

    def stop(self) -> str:
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._queue.put(None)
        if self._writer_thread is not None:
            self._writer_thread.join(timeout=10)
            self._writer_thread = None
        if self._wf is not None:
            self._wf.close()
            self._wf = None
        return str(self.wav_path)
