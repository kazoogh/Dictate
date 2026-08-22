"""HTTP client for the internal Dictate API server (Proxmox)."""

from __future__ import annotations

import json
import logging
import mimetypes
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("dictate.server")

# On macOS the OS "Local Network" privacy gate blocks Python's own network stack
# from reaching LAN servers (connections fail with errno 65, "No route to host",
# and the app can't be granted access unless it's Apple-signed). The system curl
# binary is exempt from that gate, so on macOS we route requests through it.
_USE_CURL = sys.platform == "darwin"
_CURL = "/usr/bin/curl"


class DictateServerError(Exception):
    """Raised when the Dictate API server returns an error response."""


class DictateServerClient:
    def __init__(
        self,
        base_url: str,
        *,
        api_key: str = "",
        timeout: float = 60.0,
        client_name: str = "",
        client_version: str = "",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = float(timeout)
        self.client_name = client_name.strip()
        self.client_version = client_version.strip()

    def _request_headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        if self.client_name:
            headers["x-client-name"] = self.client_name
        if self.client_version:
            headers["x-client-version"] = self.client_version
        if extra:
            headers.update(extra)
        return headers

    # ------------------------------------------------------------------ #
    # curl transport (macOS only)
    # ------------------------------------------------------------------ #
    def _curl_request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        file_path: str | None = None,
    ) -> dict[str, Any]:
        cmd = [
            _CURL, "-sS",
            "-m", str(int(self.timeout)),
            "-X", method,
            "-w", "\n%{http_code}",
        ]
        for key, value in headers.items():
            cmd += ["-H", f"{key}: {value}"]
        if file_path is not None:
            filename = Path(file_path).name
            ctype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            cmd += ["-F", f"file=@{file_path};type={ctype};filename={filename}"]
        cmd.append(url)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout + 15
            )
        except subprocess.TimeoutExpired as exc:
            raise DictateServerError("Request timed out") from exc
        except OSError as exc:
            raise DictateServerError(f"Could not run curl: {exc}") from exc

        if proc.returncode != 0:
            detail = proc.stderr.strip() or f"curl exit {proc.returncode}"
            raise DictateServerError(f"Request failed: {detail[:200]}")

        body, _, status = proc.stdout.rpartition("\n")
        status = status.strip()
        if status != "200":
            raise DictateServerError(f"Server returned status {status}: {body[:200]}")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise DictateServerError("Server returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise DictateServerError("Server returned unexpected response")
        return payload

    # ------------------------------------------------------------------ #
    def health(self) -> dict[str, Any]:
        url = f"{self.base_url}/health"
        logger.info("Dictate server health check: %s", url)
        if _USE_CURL:
            return self._curl_request("GET", url, headers=self._request_headers())

        request = Request(url, headers=self._request_headers(), method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise DictateServerError(f"Health check failed ({exc.code}): {body[:200]}") from exc
        except URLError as exc:
            raise DictateServerError(f"Health check failed: {exc.reason}") from exc
        logger.info("Dictate server health OK")
        return payload

    def transcribe(self, audio_path: str | Path) -> dict[str, Any]:
        path = Path(audio_path)
        if not path.is_file():
            raise DictateServerError(f"Audio file not found: {path}")

        url = f"{self.base_url}/transcribe"
        logger.info("Dictate server transcribe: %s (%s bytes)", url, path.stat().st_size)

        if _USE_CURL:
            payload = self._curl_request(
                "POST", url, headers=self._request_headers(), file_path=str(path)
            )
        else:
            body, content_type = _encode_multipart_file(path, field_name="file")
            headers = self._request_headers({"Content-Type": content_type})
            request = Request(url, data=body, headers=headers, method="POST")
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    status = getattr(response, "status", 200)
                    raw = response.read().decode("utf-8")
            except HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="replace")
                raise DictateServerError(
                    f"Transcribe failed ({exc.code}): {err_body[:200]}"
                ) from exc
            except URLError as exc:
                raise DictateServerError(f"Transcribe failed: {exc.reason}") from exc
            if status != 200:
                raise DictateServerError(f"Transcribe failed with status {status}")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise DictateServerError("Transcribe returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise DictateServerError("Transcribe returned unexpected response")
        text = str(payload.get("text", "")).strip()
        if not text:
            raise DictateServerError("Transcribe returned empty text")

        elapsed = payload.get("processing_time_seconds")
        logger.info(
            "Dictate server transcribe OK (%.2fs, chars=%d)",
            float(elapsed) if elapsed is not None else -1.0,
            len(text),
        )
        return payload


def _encode_multipart_file(path: Path, *, field_name: str) -> tuple[bytes, str]:
    boundary = f"----Dictate{uuid.uuid4().hex}"
    filename = path.name
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    file_data = path.read_bytes()

    parts: list[bytes] = [
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        ).encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        file_data,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    body = b"".join(parts)
    return body, f"multipart/form-data; boundary={boundary}"
