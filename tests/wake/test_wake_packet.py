"""Tests for src/wake/packet.py — building and broadcasting the magic packet.

No packet leaves the machine: ``socket.socket`` is monkeypatched with a recorder,
so these assert on the bytes, the destination and the one socket option that makes
a broadcast legal. The constants stay real — the point is that ``SO_BROADCAST`` is
set on ``SOL_SOCKET``, not that two integers can be compared to themselves.
"""

import importlib
import socket
from types import ModuleType
from typing import Any, Optional

import pytest

from src.wake.packet import DEFAULT_BROADCAST, DEFAULT_PORT, magic_packet

_module: ModuleType = importlib.import_module("src.wake.packet")

MAC = "aa:bb:cc:dd:ee:ff"
RAW = bytes.fromhex("aabbccddeeff")


class _FakeSocket:
    """Records what was done to it; raises on send if ``error`` is set."""

    def __init__(self, log: dict[str, Any], error: Optional[OSError] = None) -> None:
        self._log = log
        self._error = error
        log["family"] = None
        log["opts"] = []
        log["sent"] = []
        log["closed"] = False

    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, *exc: object) -> None:
        self._log["closed"] = True

    def setsockopt(self, level: int, option: int, value: int) -> None:
        self._log["opts"].append((level, option, value))

    def sendto(self, payload: bytes, addr: tuple[str, int]) -> None:
        if self._error:
            raise self._error
        self._log["sent"].append((payload, addr))


@pytest.fixture
def sock(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    log: dict[str, Any] = {}

    def _factory(family: int, kind: int) -> _FakeSocket:
        sock = _FakeSocket(log)
        log["family"] = (family, kind)
        return sock

    monkeypatch.setattr(_module.socket, "socket", _factory)
    return log


# ── The packet itself ─────────────────────────────────────────────────────────


def test_packet_is_the_sync_stream_then_the_mac_sixteen_times() -> None:
    assert magic_packet(MAC) == b"\xff" * 6 + RAW * 16


def test_packet_is_102_bytes() -> None:
    assert len(magic_packet(MAC)) == 102


def test_separators_are_stripped_not_encoded() -> None:
    # The colons are formatting; only the six address bytes belong on the wire.
    assert b":" not in magic_packet(MAC)


def test_uppercase_mac_builds_the_same_packet() -> None:
    # pydantic normalises to lowercase, but fromhex is case-insensitive either way.
    assert magic_packet(MAC.upper()) == magic_packet(MAC)


def test_a_malformed_mac_raises() -> None:
    with pytest.raises(ValueError):
        magic_packet("not-a-mac")


# ── Sending ───────────────────────────────────────────────────────────────────


def test_sends_one_udp_datagram_to_the_broadcast_address(sock: dict[str, Any]) -> None:
    _module.send_magic_packet(MAC)
    assert sock["family"] == (socket.AF_INET, socket.SOCK_DGRAM)
    assert sock["sent"] == [(magic_packet(MAC), (DEFAULT_BROADCAST, DEFAULT_PORT))]


def test_broadcast_is_enabled_before_sending(sock: dict[str, Any]) -> None:
    # Without SO_BROADCAST the kernel refuses the send outright.
    _module.send_magic_packet(MAC)
    assert (socket.SOL_SOCKET, socket.SO_BROADCAST, 1) in sock["opts"]


def test_the_socket_is_closed(sock: dict[str, Any]) -> None:
    _module.send_magic_packet(MAC)
    assert sock["closed"]


def test_broadcast_and_port_are_honoured(sock: dict[str, Any]) -> None:
    _module.send_magic_packet(MAC, "10.0.0.255", 7)
    assert sock["sent"][0][1] == ("10.0.0.255", 7)


def test_defaults_are_the_limited_broadcast_and_the_discard_port() -> None:
    assert DEFAULT_BROADCAST == "255.255.255.255"
    assert DEFAULT_PORT == 9


def test_an_oserror_becomes_a_valueerror_naming_via(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused send is a user mistake, so it must not surface as a traceback."""
    log: dict[str, Any] = {}
    boom = OSError("Network is unreachable")
    monkeypatch.setattr(
        _module.socket, "socket", lambda *a: _FakeSocket(log, error=boom)
    )

    with pytest.raises(ValueError) as excinfo:
        _module.send_magic_packet(MAC, "10.9.9.255", 9)

    message = str(excinfo.value)
    assert "10.9.9.255:9" in message
    assert "Network is unreachable" in message
    assert "--via" in message  # the remediation, which is the point of catching it
    assert excinfo.value.__cause__ is boom
