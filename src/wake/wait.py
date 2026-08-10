"""Waiting for a woken machine to answer.

Sending a magic packet is fire-and-forget — the protocol has no acknowledgement,
and a NAS takes a minute or two to finish spinning up — so ``--wait`` answers the
only question that matters afterwards: is it actually up?

A TCP connect rather than a ping: ICMP needs a raw socket (root) and, more to the
point, "the SSH port is open" is what makes the machine *useful*, while a box can
answer ping halfway through boot. The port is configurable because an appliance may
have SSH closed and only serve its web UI.
"""

import socket
import time
from typing import Optional

DEFAULT_WAIT_PORT = 22
# One probe's patience, and the gap between probes. Both short: the total budget is
# the caller's ``timeout``, and a machine that is up answers immediately.
_PROBE_TIMEOUT = 2.0
_INTERVAL = 3.0


def is_up(ip: str, port: int, timeout: float = _PROBE_TIMEOUT) -> bool:
    """True if something accepts a TCP connection on ``ip:port`` right now."""
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_until_up(
    ip: str, port: int = DEFAULT_WAIT_PORT, timeout: float = 120.0
) -> Optional[float]:
    """Poll ``ip:port`` until it answers. Seconds elapsed, or None if it never did."""
    started: float = time.monotonic()
    deadline: float = started + timeout

    while True:
        if is_up(ip, port):
            return time.monotonic() - started
        if time.monotonic() >= deadline:
            return None
        # Do not overshoot the deadline just to complete one more sleep.
        time.sleep(min(_INTERVAL, max(0.0, deadline - time.monotonic())))
