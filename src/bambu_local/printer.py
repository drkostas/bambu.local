"""A printer's report and commands, over the MQTT broker it runs on port 8883.

The printer answers a `pushall` request with its whole state, and that is the only interface that
says what it is doing. Only the part of MQTT this needs is written here (connect, subscribe, publish
once, read publishes), so nothing has to install on a machine that runs this unattended. It has QoS 0
only, with no keepalive, reconnect or will, because a caller asks one question and goes away. If the
printer is off, the connect fails, and that failure is the answer.

The printer's certificate is its own and cannot be checked against a public authority, so TLS here
protects the access code from a passive listener only. Use this on a network you trust.
"""
from __future__ import annotations

import json
import pathlib
import socket
import ssl
import struct
import time

#: where Bambu Studio keeps the serial to access-code pairs on macOS, and on Linux and Windows
STUDIO_CONFS = (
    pathlib.Path.home() / "Library/Application Support/BambuStudio/BambuStudio.conf",
    pathlib.Path.home() / ".config/BambuStudio/BambuStudio.conf",
    pathlib.Path.home() / "AppData/Roaming/BambuStudio/BambuStudio.conf",
)
MQTT_PORT = 8883
CLIENT_ID = "bambu-local"
USER = "bblp"


def credentials(conf: str | pathlib.Path | None = None) -> tuple[str, str] | None:
    """The first printer Bambu Studio is paired with, as (serial, access code), or None. Reading them
    from there means a code changed on the printer is picked up by pairing again in the app."""
    for path in ([pathlib.Path(conf)] if conf else STUDIO_CONFS):
        try:
            pairs = json.loads(path.read_text()).get("access_code") or {}
        except (OSError, ValueError, AttributeError):
            continue
        for serial, code in pairs.items():
            if serial and code:
                return serial, str(code)
    return None


def _remaining_length(n: int) -> bytes:
    """MQTT's variable-byte integer: seven bits a byte, and the high bit means another follows."""
    out = b""
    while True:
        byte = n % 128
        n //= 128
        out += bytes([byte | (0x80 if n else 0)])
        if not n:
            return out


def _read_remaining_length(sock) -> int:
    multiplier, value = 1, 0
    while True:
        byte = sock.recv(1)
        if not byte:
            raise ConnectionError("broker closed while reading a length")
        value += (byte[0] & 127) * multiplier
        if not byte[0] & 0x80:
            return value
        multiplier *= 128
        if multiplier > 128 ** 3:
            raise ValueError("malformed remaining length")


def _string(s: str) -> bytes:
    raw = s.encode()
    return struct.pack("!H", len(raw)) + raw


def _connect_packet(code: str, client_id: str = CLIENT_ID) -> bytes:
    """CONNECT at protocol level 4 (MQTT 3.1.1), with a username, a password and a 60 s keepalive."""
    body = _string("MQTT") + bytes([4, 0xC0]) + struct.pack("!H", 60) \
        + _string(client_id) + _string(USER) + _string(code)
    return bytes([0x10]) + _remaining_length(len(body)) + body


def _publish_packet(topic: str, message: dict) -> bytes:
    body = _string(topic) + json.dumps(message).encode()
    return bytes([0x30]) + _remaining_length(len(body)) + body


def _connect(host: str, code: str, timeout: float, port: int = MQTT_PORT):
    """Open a TLS socket and complete an MQTT CONNECT, or raise. The caller closes it."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    raw = socket.create_connection((host, port), timeout=timeout)
    sock = context.wrap_socket(raw, server_hostname=host)
    try:
        sock.settimeout(timeout)
        sock.sendall(_connect_packet(code))
        kind = sock.recv(1)
        if not kind or kind[0] >> 4 != 2:
            raise ConnectionError("no CONNACK from the printer")
        connack = sock.recv(_read_remaining_length(sock))
        if len(connack) >= 2 and connack[1] != 0:
            raise PermissionError(f"printer refused the connection (code {connack[1]})")
    except Exception:
        sock.close()
        raise
    return sock


def report(host: str, serial: str, code: str, *, timeout: float = 20.0) -> dict:
    """Connect, ask for everything, and return the merged report, or {} if the printer says nothing.

    The whole read is bounded by twice `timeout`, so a printer that keeps talking without giving its
    state cannot hold the caller."""
    with _connect(host, code, timeout) as sock:
        sub = struct.pack("!H", 1) + _string(f"device/{serial}/report") + bytes([0])
        sock.sendall(bytes([0x82]) + _remaining_length(len(sub)) + sub)
        kind = sock.recv(1)
        if kind and kind[0] >> 4 == 9:
            sock.recv(_read_remaining_length(sock))
        sock.sendall(_publish_packet(f"device/{serial}/request",
                                     {"pushing": {"sequence_id": "1", "command": "pushall"}}))
        return _read_reports(sock, deadline=time.monotonic() + 2 * timeout)


def _read_reports(sock, deadline: float, clock=None) -> dict:
    """Read MQTT packets and merge the report publishes one level deep (later ones are deltas), until
    the printer has said what it is doing, it closes, a read times out, or `deadline` passes.

    An empty read ends the loop: a closed TLS socket returns b"" for ever, so a loop that waits for a
    byte count would spin at full CPU."""
    clock = clock or time.monotonic
    merged: dict = {}
    while clock() < deadline:
        try:
            kind = sock.recv(1)
        except (TimeoutError, socket.timeout):
            break
        if not kind:
            break
        try:
            remaining = _read_remaining_length(sock)
        except (ConnectionError, ValueError):
            break
        buf = b""
        while len(buf) < remaining:
            chunk = sock.recv(min(65536, remaining - len(buf)))
            if not chunk:
                return merged
            buf += chunk
        if kind[0] >> 4 != 3:                  # not a PUBLISH: its body is read, and skipped
            continue
        topic_len = struct.unpack("!H", buf[:2])[0]
        try:
            message = json.loads(buf[2 + topic_len:])
        except ValueError:
            continue
        for key, value in message.items():
            if isinstance(value, dict):
                merged.setdefault(key, {}).update(value)
            else:
                merged[key] = value
        if merged.get("print", {}).get("gcode_state") is not None:
            break
    return merged


def command(host: str, serial: str, code: str, payload: dict, *, timeout: float = 15.0) -> None:
    """Send one command and return. Nothing here confirms it worked: at QoS 0 the broker accepts the
    publish whether or not the firmware acts on it, so read `report` afterwards and compare."""
    with _connect(host, code, timeout) as sock:
        sock.sendall(_publish_packet(f"device/{serial}/request", payload))
