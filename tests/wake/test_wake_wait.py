"""Tests for src/wake/wait.py — polling until a woken machine answers.

Nothing connects and nothing sleeps: ``socket`` is stubbed for ``is_up``, and the
whole ``time`` module the poller uses is replaced with a fake clock that advances
only when the code under test sleeps. That makes the timing assertions exact —
including the one that matters, that the last sleep is trimmed so a wait never
overshoots its deadline.
"""

import importlib
from types import ModuleType
from typing import Optional

import pytest

from src.wake import DEFAULT_WAIT_PORT

_module: ModuleType = importlib.import_module("src.wake.wait")


class _Clock:
    """A monotonic clock that only moves when something sleeps on it."""

    def __init__(self) -> None:
        self.now: float = 0.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(_module, "time", fake)
    return fake


# ── is_up ─────────────────────────────────────────────────────────────────────


class _FakeConn:
    def __enter__(self) -> "_FakeConn":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def test_is_up_is_true_when_the_port_accepts(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def _connect(addr: tuple[str, int], timeout: float) -> _FakeConn:
        seen["addr"] = addr
        seen["timeout"] = timeout
        return _FakeConn()

    monkeypatch.setattr(_module.socket, "create_connection", _connect)

    assert _module.is_up("10.0.0.5", 22) is True
    assert seen["addr"] == ("10.0.0.5", 22)
    # A probe must not block for the whole wait budget.
    assert seen["timeout"] == _module._PROBE_TIMEOUT


def test_is_up_is_false_when_the_connection_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A refused/timed-out connect is the normal state of a booting box, not an error."""

    def _refuse(addr: tuple[str, int], timeout: float) -> _FakeConn:
        raise OSError("Connection refused")

    monkeypatch.setattr(_module.socket, "create_connection", _refuse)
    assert _module.is_up("10.0.0.5", 22) is False


def test_the_default_wait_port_is_ssh() -> None:
    assert DEFAULT_WAIT_PORT == 22


# ── wait_until_up ─────────────────────────────────────────────────────────────


def test_a_machine_that_is_already_up_returns_immediately(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_module, "is_up", lambda *a, **kw: True)

    elapsed: Optional[float] = _module.wait_until_up("10.0.0.5", 22, timeout=120.0)

    assert elapsed == 0.0
    assert clock.slept == []  # no waiting when there is nothing to wait for


def test_it_polls_until_the_port_answers(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes: list[bool] = []

    def _is_up(ip: str, port: int, timeout: float = 0.0) -> bool:
        up: bool = len(probes) >= 2  # fails twice, then answers
        probes.append(up)
        return up

    monkeypatch.setattr(_module, "is_up", _is_up)

    elapsed: Optional[float] = _module.wait_until_up("10.0.0.5", 22, timeout=120.0)

    assert len(probes) == 3
    assert clock.slept == [_module._INTERVAL, _module._INTERVAL]
    assert elapsed == 2 * _module._INTERVAL


def test_a_machine_that_never_answers_returns_none(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_module, "is_up", lambda *a, **kw: False)

    assert _module.wait_until_up("10.0.0.5", 22, timeout=10.0) is None


def test_the_last_sleep_is_trimmed_to_the_deadline(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Otherwise a 10s wait would sleep past 12s just to finish one more interval."""
    monkeypatch.setattr(_module, "is_up", lambda *a, **kw: False)

    _module.wait_until_up("10.0.0.5", 22, timeout=10.0)

    assert clock.slept == [3.0, 3.0, 3.0, 1.0]
    assert sum(clock.slept) == 10.0
    assert clock.now == 10.0


def test_a_zero_timeout_still_probes_once(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--wait 0 never reaches here, but a deadline already passed must not sleep."""
    probes: list[tuple[str, int]] = []

    def _is_up(ip: str, port: int) -> bool:
        probes.append((ip, port))
        return False

    monkeypatch.setattr(_module, "is_up", _is_up)

    assert _module.wait_until_up("10.0.0.5", 22, timeout=0.0) is None
    assert len(probes) == 1
    assert clock.slept == []


def test_the_probed_address_is_passed_through(
    clock: _Clock, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes: list[tuple[str, int]] = []

    def _is_up(ip: str, port: int) -> bool:
        probes.append((ip, port))
        return True

    monkeypatch.setattr(_module, "is_up", _is_up)

    _module.wait_until_up("10.0.0.5", 8006)
    assert probes == [("10.0.0.5", 8006)]
