"""Tests for src/dns/pihole/client.py that need no Pi-hole.

Everything here is about the session and the transport's own bookkeeping, so
``_request`` is replaced rather than a server stood up. What the API *returns* is
covered where a fake server is worth the setup; what matters below is that the
client hands back its session slot no matter how the call went, since FTL has a
small fixed number of them.
"""

import ssl
from typing import Optional

import pytest

from src.dns.errors import DnsBackendError
from src.dns.pihole.client import PiholeClient, PiholeError


def _client(**kwargs: object) -> PiholeClient:
    return PiholeClient("10.0.0.53", "hunter2", **kwargs)


# ── the address it talks to ───────────────────────────────────────────────────


def test_the_base_url_is_built_from_scheme_address_and_port() -> None:
    assert _client(scheme="https", port=443)._base == "https://10.0.0.53:443/api"
    assert _client(scheme="http", port=8080)._base == "http://10.0.0.53:8080/api"


def test_https_gets_an_unverified_context_since_the_cert_is_self_signed() -> None:
    context: Optional[ssl.SSLContext] = _client(scheme="https")._ssl_context
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_NONE
    assert context.check_hostname is False


def test_http_needs_no_ssl_context() -> None:
    assert _client(scheme="http")._ssl_context is None


# ── errors ────────────────────────────────────────────────────────────────────


def test_a_pihole_error_is_a_dns_backend_error() -> None:
    """The CLI catches one type across every backend."""
    assert issubclass(PiholeError, DnsBackendError)


def test_a_pihole_error_carries_the_status_for_callers_to_branch_on() -> None:
    """`get_hosts` falls back on 404 rather than matching message text."""
    assert PiholeError("nope", status=404).status == 404
    assert PiholeError("nope").status is None


# ── releasing the session ─────────────────────────────────────────────────────


def test_closing_without_a_session_does_nothing() -> None:
    client = _client()
    client.close()  # must not raise, and must not call out
    assert client._sid is None


def test_closing_releases_the_slot_and_forgets_the_session() -> None:
    client = _client()
    client._sid, client._csrf = "sid-1", "csrf-1"
    calls: list[tuple[str, str]] = []
    client._request = lambda method, path, payload=None: (  # type: ignore[method-assign]
        calls.append((method, path)) or None
    )

    client.close()

    assert calls == [("DELETE", "/auth")]
    assert client._sid is None
    assert client._csrf is None


@pytest.mark.parametrize(
    "failure",
    [PiholeError("the server went away"), OSError("connection reset"), RuntimeError()],
    ids=["pihole-error", "os-error", "unexpected"],
)
def test_closing_never_raises_whatever_the_logout_does(failure: Exception) -> None:
    """It runs on the way out, often while another exception is propagating.

    Letting this one through would replace the error that actually matters with
    one about a session nobody is going to use again.
    """
    client = _client()
    client._sid = "sid-1"

    def boom(method: str, path: str, payload: Optional[dict] = None) -> None:
        raise failure

    client._request = boom  # type: ignore[method-assign]

    client.close()  # the assertion is that this returns at all

    assert client._sid is None
    assert client._csrf is None


def test_the_context_manager_logs_in_and_out_around_the_body() -> None:
    client = _client()
    events: list[str] = []
    client.login = lambda: events.append("login")  # type: ignore[method-assign]
    client.close = lambda: events.append("close")  # type: ignore[method-assign]

    with client as entered:
        assert entered is client
        events.append("body")

    assert events == ["login", "body", "close"]


def test_the_session_is_released_even_when_the_body_raises() -> None:
    client = _client()
    events: list[str] = []
    client.login = lambda: events.append("login")  # type: ignore[method-assign]
    client.close = lambda: events.append("close")  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        with client:
            raise ValueError("diff blew up halfway")

    assert events == ["login", "close"]
