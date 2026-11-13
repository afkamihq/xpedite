"""The smallest WebSocket client that Discord's gateway needs, on the standard library only (ssl +
socket): text frames out (masked, as a client must), text/close/ping frames in, pong replies.
No compression, no extensions. Thread-safe sending; one reader.

Kept tiny on purpose (user, 12 Nov 2026: "really low ram usage"): no aiohttp/websockets.
"""
from __future__ import annotations

import base64
import os
import socket
import ssl
import struct
import threading
from urllib.parse import urlparse

TEXT, BINARY, CLOSE, PING, PONG = 0x1, 0x2, 0x8, 0x9, 0xA


class WebSocketClosed(Exception):
    def __init__(self, code: int | None = None, reason: str = ""):
        super().__init__(f"websocket closed ({code}) {reason}".strip())
        self.code, self.reason = code, reason


class WebSocket:
    def __init__(self, url: str, timeout: float = 30.0):
        parsed = urlparse(url)
        host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        raw = socket.create_connection((host, port), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host) \
            if parsed.scheme == "wss" else raw
        self._send_lock = threading.Lock()
        self._buffer = b""
        key = base64.b64encode(os.urandom(16)).decode()
        request = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                   f"User-Agent: afkami-xpedite\r\n\r\n")
        self.sock.sendall(request.encode())
        head = self._read_until(b"\r\n\r\n")
        status = head.split(b"\r\n", 1)[0]
        if b" 101 " not in status:
            raise ConnectionError(f"websocket handshake refused: {status!r}")

    # ------------------------------------------------------------------ reading
    def _read_exact(self, n: int) -> bytes:
        while len(self._buffer) < n:
            chunk = self.sock.recv(max(65536, n - len(self._buffer)))
            if not chunk:
                raise WebSocketClosed(None, "connection lost")
            self._buffer += chunk
        data, self._buffer = self._buffer[:n], self._buffer[n:]
        return data

    def _read_until(self, marker: bytes) -> bytes:
        while marker not in self._buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("connection closed during the handshake")
            self._buffer += chunk
        head, self._buffer = self._buffer.split(marker, 1)
        return head

    def recv(self) -> str:
        """The next whole text message. Answers pings; raises WebSocketClosed on a close frame."""
        message, opcode = b"", None
        while True:
            b0, b1 = self._read_exact(2)
            fin, op = b0 & 0x80, b0 & 0x0F
            length = b1 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            mask = self._read_exact(4) if b1 & 0x80 else None
            payload = self._read_exact(length)
            if mask:
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            if op == PING:
                self._send_frame(PONG, payload)
                continue
            if op == PONG:
                continue
            if op == CLOSE:
                code = struct.unpack(">H", payload[:2])[0] if len(payload) >= 2 else None
                raise WebSocketClosed(code, payload[2:].decode(errors="replace"))
            if op in (TEXT, BINARY):
                opcode = op
            message += payload
            if fin:
                return message.decode() if opcode == TEXT else message.decode(errors="replace")

    # ------------------------------------------------------------------ writing
    def _send_frame(self, opcode: int, payload: bytes):
        header = bytes([0x80 | opcode])
        length = len(payload)
        if length < 126:
            header += bytes([0x80 | length])
        elif length < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", length)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", length)
        mask = os.urandom(4)
        masked = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        with self._send_lock:
            self.sock.sendall(header + mask + masked)

    def send(self, text: str):
        self._send_frame(TEXT, text.encode())

    def close(self, code: int = 1000):
        try:
            self._send_frame(CLOSE, struct.pack(">H", code))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
