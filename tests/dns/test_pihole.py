"""Tests for src/dns/pihole.py — the dns.hosts wire format and the v6 API client.

No network: ``urlopen`` is replaced by a stub that routes on (method, path) and
records what was sent, so the auth handshake, the session headers and the exact
PATCH body are all assertable.
"""

import email.message
import io
import json
import urllib.error
import urllib.request
from ipaddress import IPv4Address
from typing import Optional

import pytest

from src.dns import PiholeClient, PiholeError, format_host_line, parse_hosts

# ─── Wire format ──────────────────────────────────────────────────────────────


def test_format_host_line() -> None:
    assert format_host_line(IPv4Address("10.0.0.5"), "nas.lab") == "10.0.0.5 nas.lab"


def test_parse_plain_lines() -> None:
    records, unparsed = parse_hosts(["10.0.0.5 nas.lab", "10.0.0.6 docker.lab"])
    assert [(r.hostname, str(r.ip)) for r in records] == [
        ("nas.lab", "10.0.0.5"),
        ("docker.lab", "10.0.0.6"),
    ]
    assert unparsed == []


def test_parse_line_with_several_names() -> None:
    # dnsmasq allows `<ip> <name> <name>`; each name is its own record.
    records, unparsed = parse_hosts(["10.0.0.20 hass.lab ha.lab"])
    assert [r.hostname for r in records] == ["hass.lab", "ha.lab"]
    assert {str(r.ip) for r in records} == {"10.0.0.20"}
    assert unparsed == []


def test_parse_tolerates_extra_whitespace() -> None:
    records, _ = parse_hosts(["  10.0.0.5\tnas.lab  "])
    assert [(r.hostname, str(r.ip)) for r in records] == [("nas.lab", "10.0.0.5")]


@pytest.mark.parametrize("line", ["", "   ", "10.0.0.5", "not-an-ip nas.lab", "::1 v6"])
def test_unreadable_lines_are_reported_not_dropped(line: str) -> None:
    # A sync rewrites the whole array, so anything unparsed is about to be lost and
    # has to be surfaced rather than silently discarded.
    records, unparsed = parse_hosts([line])
    assert records == []
    assert unparsed == [line]


def test_mixed_good_and_bad_lines() -> None:
    records, unparsed = parse_hosts(["10.0.0.5 nas.lab", "garbage"])
    assert [r.hostname for r in records] == ["nas.lab"]
    assert unparsed == ["garbage"]


# ─── Client ───────────────────────────────────────────────────────────────────


def _sent_json(request: urllib.request.Request) -> dict:
    """The JSON body a Request carries, narrowed from Request.data's loose type."""
    data: object = request.data
    assert isinstance(data, bytes)
    return json.loads(data)


class _Response:
    def __init__(self, payload: Optional[dict]) -> None:
        self._raw: bytes = b"" if payload is None else json.dumps(payload).encode()

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _Api:
    """Stand-in for ``urlopen``: answers the four endpoints and records requests."""

    def __init__(self, hosts: Optional[list[str]] = None) -> None:
        self.hosts: list[str] = hosts if hosts is not None else []
        self.requests: list[urllib.request.Request] = []
        self.patched: Optional[dict] = None
        self.session_valid: bool = True

    def __call__(
        self,
        request: urllib.request.Request,
        timeout: object = None,
        context: object = None,
    ) -> _Response:
        self.requests.append(request)
        path: str = request.full_url.split("/api", 1)[1]
        route: tuple[Optional[str], str] = (request.method, path)

        if route == ("POST", "/auth"):
            return _Response(
                {
                    "session": {
                        "valid": self.session_valid,
                        "sid": "SID-1" if self.session_valid else None,
                        "csrf": "CSRF-1",
                    }
                }
            )
        if route == ("GET", "/config/dns/hosts"):
            return _Response({"config": {"dns": {"hosts": self.hosts}}})
        if route == ("PATCH", "/config"):
            self.patched = _sent_json(request)
            return _Response({})
        if route == ("DELETE", "/auth"):
            return _Response(None)
        raise AssertionError(f"unexpected call: {request.method} {path}")

    # helpers
    def methods(self) -> list[Optional[str]]:
        return [r.method for r in self.requests]

    def header(self, index: int, name: str) -> Optional[str]:
        headers = {k.lower(): v for k, v in self.requests[index].header_items()}
        return headers.get(name.lower())


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> _Api:
    stub = _Api()
    monkeypatch.setattr(urllib.request, "urlopen", stub)
    return stub


def _client() -> PiholeClient:
    return PiholeClient("10.0.0.53", "secret", port=8080)


def test_login_posts_the_password(api: _Api) -> None:
    _client().login()
    assert api.methods() == ["POST"]
    assert _sent_json(api.requests[0]) == {"password": "secret"}
    assert api.requests[0].full_url == "http://10.0.0.53:8080/api/auth"


def test_session_headers_are_sent_after_login(api: _Api) -> None:
    client = _client()
    client.login()
    client.get_hosts()
    # The auth request carries no session; everything after it does.
    assert api.header(0, "X-FTL-SID") is None
    assert api.header(1, "X-FTL-SID") == "SID-1"
    assert api.header(1, "X-FTL-CSRF") == "CSRF-1"


def test_get_hosts_parses_the_array(api: _Api) -> None:
    api.hosts = ["10.0.0.5 nas.lab", "10.0.0.6 docker.lab"]
    client = _client()
    client.login()
    records, unparsed = client.get_hosts()
    assert [r.hostname for r in records] == ["nas.lab", "docker.lab"]
    assert unparsed == []


def test_set_hosts_patches_the_whole_array(api: _Api) -> None:
    client = _client()
    client.login()
    client.set_hosts(
        [(IPv4Address("10.0.0.5"), "nas.lab"), (IPv4Address("10.0.0.6"), "docker.lab")]
    )
    assert api.patched == {
        "config": {"dns": {"hosts": ["10.0.0.5 nas.lab", "10.0.0.6 docker.lab"]}}
    }


def test_context_manager_logs_in_and_releases_the_session(api: _Api) -> None:
    with _client() as client:
        client.get_hosts()
    assert api.methods() == ["POST", "GET", "DELETE"]


def test_session_released_even_when_the_body_raises(api: _Api) -> None:
    with pytest.raises(RuntimeError):
        with _client():
            raise RuntimeError("boom")
    assert api.methods() == ["POST", "DELETE"]


def test_rejected_password_raises_pihole_error(api: _Api) -> None:
    api.session_valid = False
    with pytest.raises(PiholeError, match="rejected the API password"):
        _client().login()


def test_missing_hosts_array_raises_pihole_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _reply(request: urllib.request.Request, **_: object) -> _Response:
        if request.method == "POST":
            return _Response({"session": {"valid": True, "sid": "S", "csrf": "C"}})
        return _Response({"config": {"dns": {}}})

    monkeypatch.setattr(urllib.request, "urlopen", _reply)
    client = _client()
    client.login()
    with pytest.raises(PiholeError, match="no dns.hosts array"):
        client.get_hosts()


def _raise(error: Exception, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_: object, **__: object) -> None:
        raise error

    monkeypatch.setattr(urllib.request, "urlopen", _boom)


def test_unauthenticated_response_is_explained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _raise(
        urllib.error.HTTPError("http://x/api/auth", 401, "Unauthorized", email.message.Message(), None),
        monkeypatch,
    )
    with pytest.raises(PiholeError, match="unauthenticated"):
        _client().login()


def test_404_points_at_the_pihole_version(monkeypatch: pytest.MonkeyPatch) -> None:
    _raise(
        urllib.error.HTTPError("http://x/api/auth", 404, "Not Found", email.message.Message(), None),
        monkeypatch,
    )
    with pytest.raises(PiholeError, match="Pi-hole v6"):
        _client().login()


def test_http_error_detail_is_surfaced(monkeypatch: pytest.MonkeyPatch) -> None:
    body = io.BytesIO(json.dumps({"error": {"message": "bad request"}}).encode())
    _raise(
        urllib.error.HTTPError("http://x/api/config", 400, "Bad Request", email.message.Message(), body),
        monkeypatch,
    )
    with pytest.raises(PiholeError, match="bad request"):
        _client().login()


def test_unreachable_host_names_the_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    _raise(urllib.error.URLError("Connection refused"), monkeypatch)
    with pytest.raises(PiholeError, match="pihole_location"):
        _client().login()


def test_non_json_reply_is_explained(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Html:
        def read(self) -> bytes:
            return b"<html>login page</html>"

        def __enter__(self) -> "_Html":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Html())
    with pytest.raises(PiholeError, match="non-JSON reply"):
        _client().login()


def test_json_array_reply_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Array:
        def read(self) -> bytes:
            return b"[1, 2]"

        def __enter__(self) -> "_Array":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Array())
    with pytest.raises(PiholeError, match="rather than an object"):
        _client().login()


def test_https_scheme_builds_an_https_base(api: _Api) -> None:
    PiholeClient("10.0.0.53", "secret", scheme="https", port=443).login()
    assert api.requests[0].full_url.startswith("https://10.0.0.53:443/api")


def test_get_hosts_falls_back_to_the_whole_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A build that does not serve the dns.hosts leaf still works via /config."""
    seen: list[str] = []

    def _reply(request: urllib.request.Request, **_: object) -> _Response:
        path: str = request.full_url.split("/api", 1)[1]
        seen.append(path)
        if request.method == "POST":
            return _Response({"session": {"valid": True, "sid": "S", "csrf": "C"}})
        if path == "/config/dns/hosts":
            raise urllib.error.HTTPError(
                request.full_url, 404, "Not Found", email.message.Message(), None
            )
        return _Response({"config": {"dns": {"hosts": ["10.0.0.5 nas.lab"]}}})

    monkeypatch.setattr(urllib.request, "urlopen", _reply)
    client = _client()
    client.login()
    records, _ = client.get_hosts()
    assert [r.hostname for r in records] == ["nas.lab"]
    assert seen == ["/auth", "/config/dns/hosts", "/config"]


def test_get_hosts_does_not_retry_on_other_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only a 404 means "wrong endpoint"; a 401 must surface as-is.
    def _reply(request: urllib.request.Request, **_: object) -> _Response:
        if request.method == "POST":
            return _Response({"session": {"valid": True, "sid": "S", "csrf": "C"}})
        raise urllib.error.HTTPError(
            request.full_url, 401, "Unauthorized", email.message.Message(), None
        )

    monkeypatch.setattr(urllib.request, "urlopen", _reply)
    client = _client()
    client.login()
    with pytest.raises(PiholeError, match="unauthenticated"):
        client.get_hosts()


def test_pihole_error_carries_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    _raise(
        urllib.error.HTTPError(
            "http://x/api/auth", 503, "Unavailable", email.message.Message(), None
        ),
        monkeypatch,
    )
    with pytest.raises(PiholeError) as caught:
        _client().login()
    assert caught.value.status == 503
