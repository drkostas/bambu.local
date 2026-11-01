"""The printer's own storage, over implicit FTPS on port 990.

A file put here starts nothing. The printer lists it on its screen and a person presses print, or a
`project_file` command starts it. The login is the user `bblp` and the printer's access code. The data
connection must reuse the control connection's TLS session or the printer refuses it, which plain
`ftplib.FTP_TLS` does not do. The certificate cannot be checked, as with `bambu_local.printer`.
"""
from __future__ import annotations

import ftplib
import os
import pathlib
import socket
import ssl

from .printer import USER

FTPS_PORT = 990


class _ImplicitFTPS(ftplib.FTP_TLS):
    """FTP_TLS that opens with TLS at once and reuses that session on each data connection."""

    def connect(self, host="", port=FTPS_PORT, timeout=60.0, source_address=None):
        self.host, self.port, self.timeout = host, port, timeout
        raw = socket.create_connection((host, port), timeout)
        self.sock = self.context.wrap_socket(raw, server_hostname=host)
        self.af = self.sock.family
        self.file = self.sock.makefile("r", encoding=self.encoding)
        self.welcome = self.getresp()
        return self.welcome

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def _open(host: str, code: str, timeout: float, port: int = FTPS_PORT) -> _ImplicitFTPS:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    ftp = _ImplicitFTPS(context=context)
    ftp.connect(host, port, timeout)
    try:
        ftp.login(USER, code, secure=False)
        ftp.prot_p()
    except Exception:
        ftp.close()
        raise
    return ftp


def _parse_list(lines: list[str]) -> list[dict]:
    """Unix `LIST` lines -> [{"name", "size"}], folders left out."""
    out = []
    for line in lines:
        parts = line.split(None, 8)
        if len(parts) == 9 and parts[4].isdigit() and not line.startswith("d"):
            out.append({"name": parts[8], "size": int(parts[4])})
    return out


def files(host: str, code: str, folder: str = "/", *, timeout: float = 60.0) -> list[dict]:
    """The files in `folder` on the printer, as [{"name", "size"}]."""
    ftp = _open(host, code, timeout)
    try:
        lines: list[str] = []
        ftp.retrlines(f"LIST {folder}", lines.append)
        return _parse_list(lines)
    finally:
        ftp.close()


def upload(host: str, code: str, local: str | os.PathLike, remote: str | None = None, *,
           timeout: float = 300.0) -> dict:
    """Copy `local` to `remote` on the printer (its own name in the top folder by default), starting
    nothing. Raises unless the printer then lists it at the same size. Returns {"name", "size"}."""
    path = pathlib.Path(local)
    remote = remote or f"/{path.name}"
    size = path.stat().st_size
    ftp = _open(host, code, timeout)
    try:
        with path.open("rb") as f:
            ftp.storbinary(f"STOR {remote}", f)
        folder, _, name = remote.rpartition("/")
        lines: list[str] = []
        ftp.retrlines(f"LIST {folder or '/'}", lines.append)
    finally:
        ftp.close()
    for entry in _parse_list(lines):
        if entry["name"] == name and entry["size"] == size:
            return entry
    raise OSError(f"{remote} is not on the printer at {size} bytes after the upload")


def delete(host: str, code: str, remote: str, *, timeout: float = 60.0) -> None:
    """Remove one file from the printer's storage. This cannot be undone."""
    ftp = _open(host, code, timeout)
    try:
        ftp.delete(remote)
    finally:
        ftp.close()
