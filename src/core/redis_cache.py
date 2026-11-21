"""Small Redis GET/SET adapter using the standard library RESP protocol."""

from __future__ import annotations

import socket
import ssl
from urllib.parse import unquote, urlparse

from src.core.config import REDIS_URL


class RedisCacheError(RuntimeError):
    pass


def _encode_command(*parts: str) -> bytes:
    encoded = [part.encode("utf-8") for part in parts]
    return b"*%d\r\n" % len(encoded) + b"".join(
        b"$%d\r\n%s\r\n" % (len(part), part) for part in encoded
    )


def _read_response(stream):
    marker = stream.read(1)
    line = stream.readline()
    if not marker or not line.endswith(b"\r\n"):
        raise RedisCacheError("Redis returned an incomplete response")
    value = line[:-2]
    if marker == b"+":
        return value.decode("utf-8")
    if marker == b"-":
        raise RedisCacheError(value.decode("utf-8", errors="replace"))
    if marker == b":":
        return int(value)
    if marker == b"$":
        length = int(value)
        if length == -1:
            return None
        data = stream.read(length)
        if stream.read(2) != b"\r\n":
            raise RedisCacheError("Redis returned an incomplete bulk response")
        return data
    raise RedisCacheError("Redis returned an unsupported response")


def _execute(*command: str):
    parsed = urlparse(REDIS_URL)
    if parsed.scheme not in ("redis", "rediss") or not parsed.hostname:
        raise RedisCacheError("REDIS_URL must use redis:// or rediss://")
    database = (parsed.path or "/0").strip("/") or "0"
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 6379), timeout=2) as raw:
            connection = (
                ssl.create_default_context().wrap_socket(raw, server_hostname=parsed.hostname)
                if parsed.scheme == "rediss"
                else raw
            )
            with connection, connection.makefile("rb") as stream:
                if parsed.password is not None:
                    username = unquote(parsed.username) if parsed.username else None
                    password = unquote(parsed.password)
                    auth = ("AUTH", username, password) if username else ("AUTH", password)
                    connection.sendall(_encode_command(*auth))
                    _read_response(stream)
                if database != "0":
                    connection.sendall(_encode_command("SELECT", database))
                    _read_response(stream)
                connection.sendall(_encode_command(*command))
                return _read_response(stream)
    except (OSError, ValueError) as exc:
        raise RedisCacheError("Could not connect to Redis") from exc


def get_text(key: str) -> str | None:
    value = _execute("GET", key)
    return value.decode("utf-8") if value is not None else None


def set_text(key: str, value: str, ttl_seconds: int) -> None:
    _execute("SET", key, value, "EX", str(ttl_seconds))
