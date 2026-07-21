"""Microphone discovery with hot-plug friendly re-probing (Windows/PortAudio)."""

from __future__ import annotations

import threading
import time

import sounddevice as sd

# PortAudio is not thread-safe. All sounddevice access must hold this lock.
_pa_lock = threading.RLock()


def refresh_audio_devices() -> None:
    """Force PortAudio to rebuild its device list after plug/unplug."""
    with _pa_lock:
        try:
            sd._terminate()
        except Exception:
            pass
        try:
            sd._initialize()
        except Exception:
            pass
        # Give Windows a beat to finish device enumeration after USB plug.
        time.sleep(0.15)


def list_input_devices() -> list[tuple[int, str]]:
    """Return (device_index, name) for all input-capable devices."""
    with _pa_lock:
        devices: list[tuple[int, str]] = []
        try:
            for index, info in enumerate(sd.query_devices()):
                if int(info.get("max_input_channels", 0)) > 0:
                    devices.append((index, str(info.get("name", f"Device {index}"))))
        except Exception:
            pass
        return devices


def count_input_devices() -> int:
    return len(list_input_devices())


def input_device_signature() -> tuple:
    """Stable signature of available inputs + current default.

    Used to detect headset swaps even when the device count stays the same.
    """
    with _pa_lock:
        devices = list_input_devices()
        default = pick_input_device()
        default_name = ""
        if default is not None:
            try:
                default_name = str(sd.query_devices(default).get("name", ""))
            except Exception:
                default_name = f"Device {default}"
        return (default, default_name, tuple(devices))


def pick_input_device() -> int | None:
    """Pick the current default input device, or the first available input."""
    with _pa_lock:
        try:
            default = sd.default.device
            if isinstance(default, (tuple, list)):
                candidate = default[0]
            else:
                candidate = default
            if candidate is not None and int(candidate) >= 0:
                info = sd.query_devices(int(candidate))
                if int(info.get("max_input_channels", 0)) > 0:
                    return int(candidate)
        except Exception:
            pass

        for index, _name in list_input_devices():
            return index
        return None


def describe_input_device(device: int | None) -> str:
    if device is None:
        return "none"
    with _pa_lock:
        try:
            return str(sd.query_devices(device).get("name", f"Device {device}"))
        except Exception:
            return f"Device {device}"


def open_input_stream(
    *,
    samplerate: int,
    channels: int,
    dtype: str,
    callback,
    blocksize: int | None = None,
    max_attempts: int = 4,
) -> tuple[sd.InputStream, int]:
    """Open an input stream, refreshing devices between attempts."""
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        with _pa_lock:
            if attempt > 0:
                refresh_audio_devices()
            device = pick_input_device()
            if device is None:
                last_exc = OSError("No input device (-1)")
            else:
                try:
                    kwargs: dict = {
                        "samplerate": samplerate,
                        "channels": channels,
                        "dtype": dtype,
                        "callback": callback,
                        "device": device,
                    }
                    if blocksize is not None:
                        kwargs["blocksize"] = blocksize
                    stream = sd.InputStream(**kwargs)
                    stream.start()
                    return stream, device
                except Exception as exc:
                    last_exc = exc
        time.sleep(0.3 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    raise OSError("No microphone input device available")
