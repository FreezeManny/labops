"""Talking to a Pi-hole v6 instance over its REST API.

labops reads Pi-hole's ``dns.hosts`` array (see wire.py), diffs it against the
config, and writes the whole array back. Publishing therefore needs no SSH, no
dnsmasq drop-in and no service restart: FTL applies a config change itself.

Only the standard library is used, deliberately — labops carries no HTTP client
dependency and this is three requests.

The session: ``POST /api/auth`` exchanges the password for a short-lived SID and a
CSRF token, which every later request carries. FTL has a small fixed number of
session slots, so ``close()`` gives ours back instead of leaving it to expire.
"""

import json
import ssl
import urllib.error
import urllib.request
from ipaddress import IPv4Address
from types import TracebackType
from typing import Optional, Type

from models.dns.record import LiveRecord
from src.dns.errors import DnsBackendError
from src.dns.pihole.wire import format_host_line, parse_hosts

_TIMEOUT_SECONDS = 10


class PiholeError(DnsBackendError):
    """A Pi-hole API call failed. The message is written to be shown to the user.

    ``status`` carries the HTTP code when there was one, so a caller can branch on
    it (``get_hosts`` falls back to a broader endpoint on 404) rather than matching
    against the message text.
    """

    def __init__(self, message: str, status: Optional[int] = None) -> None:
        super().__init__(message)
        self.status = status


# ─── Client ───────────────────────────────────────────────────────────────────


class PiholeClient:
    """A logged-in session against one Pi-hole v6 API.

    Use it as a context manager so the session is released even when a diff or an
    apply raises partway through.
    """

    def __init__(
        self,
        address: str,
        password: str,
        *,
        scheme: str = "http",
        port: int = 80,
        timeout: int = _TIMEOUT_SECONDS,
    ) -> None:
        self.address = address
        self._base: str = f"{scheme}://{address}:{port}/api"
        self._password = password
        self._timeout = timeout
        self._sid: Optional[str] = None
        self._csrf: Optional[str] = None
        # Pi-hole's HTTPS cert is self-signed out of the box, so verifying it would
        # reject nearly every real instance. Same reasoning as a `https: true`
        # proxy upstream (see src/proxy/render.py): this is a hop across the LAN to
        # a host the config already names by address.
        self._ssl_context: Optional[ssl.SSLContext] = (
            ssl._create_unverified_context() if scheme == "https" else None
        )

    # ── session ──

    def __enter__(self) -> "PiholeClient":
        self.login()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.close()

    def login(self) -> None:
        """Exchange the password for a session SID + CSRF token."""
        body: Optional[dict] = self._request(
            "POST", "/auth", {"password": self._password}
        )
        session: dict = (body or {}).get("session") or {}
        sid: Optional[str] = session.get("sid")
        if not session.get("valid") or not sid:
            raise PiholeError(
                f"{self.address} rejected the API password. Check "
                "PIHOLE_PASSWORD in your .env (or settings.dns.pihole.password) — "
                "Pi-hole "
                "v6 wants the web-interface password or an application password."
            )
        self._sid = sid
        self._csrf = session.get("csrf")

    def close(self) -> None:
        """Release the session slot. Never raises — this runs on the way out."""
        if self._sid is None:
            return
        try:
            self._request("DELETE", "/auth")
        except Exception:
            pass
        finally:
            self._sid = None
            self._csrf = None

    # ── records ──

    def get_hosts(self) -> tuple[list[LiveRecord], list[str]]:
        """The records Pi-hole currently serves, plus any lines labops could not read.

        Asks for the ``dns.hosts`` leaf and falls back to the whole config tree if
        this build does not serve that sub-path. Either reply nests the value the
        same way, so one accessor handles both.
        """
        try:
            body: Optional[dict] = self._request("GET", "/config/dns/hosts")
        except PiholeError as e:
            if e.status != 404:
                raise
            body = self._request("GET", "/config")

        try:
            lines: list[str] = (body or {})["config"]["dns"]["hosts"]
        except (KeyError, TypeError) as e:
            raise PiholeError(
                f"{self.address} returned no dns.hosts array — is it really "
                f"Pi-hole v6? (unexpected response shape: {e})"
            ) from e
        return parse_hosts(lines)

    def set_hosts(self, records: list[tuple[IPv4Address, str]]) -> None:
        """Replace the whole ``dns.hosts`` array.

        One PATCH rather than per-record add/delete calls: the array is replaced
        atomically, so a sync cannot leave DNS half-updated if the connection drops
        mid-run.
        """
        lines: list[str] = [format_host_line(ip, hostname) for ip, hostname in records]
        self._request("PATCH", "/config", {"config": {"dns": {"hosts": lines}}})

    # ── transport ──

    def _request(
        self, method: str, path: str, payload: Optional[dict] = None
    ) -> Optional[dict]:
        """One API call, returning the decoded JSON body (None when empty).

        Every failure mode — unreachable host, wrong password, non-JSON reply —
        becomes a PiholeError whose message names the instance, since with several
        targets configured "connection refused" alone would not say which one.
        """
        url: str = f"{self._base}{path}"
        data: Optional[bytes] = (
            json.dumps(payload).encode("utf-8") if payload is not None else None
        )
        request = urllib.request.Request(url=url, data=data, method=method)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        if self._sid:
            request.add_header("X-FTL-SID", self._sid)
        if self._csrf:
            request.add_header("X-FTL-CSRF", self._csrf)

        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout, context=self._ssl_context
            ) as response:
                raw: bytes = response.read()
        except urllib.error.HTTPError as e:
            raise PiholeError(self._http_error_message(e, path), status=e.code) from e
        except urllib.error.URLError as e:
            raise PiholeError(
                f"could not reach the Pi-hole API at {url}: {e.reason}. Check "
                "settings.dns.pihole — its node/stack/address, port and scheme."
            ) from e
        except TimeoutError as e:
            raise PiholeError(f"the Pi-hole API at {url} timed out.") from e

        if not raw:
            return None
        try:
            body: object = json.loads(raw)
        except json.JSONDecodeError as e:
            raise PiholeError(
                f"{self.address} returned a non-JSON reply to {method} {path}. The "
                "address may be serving something other than the Pi-hole v6 API."
            ) from e
        if not isinstance(body, dict):
            raise PiholeError(
                f"{self.address} returned a JSON {type(body).__name__} rather than "
                f"an object for {method} {path}; expected the Pi-hole v6 API."
            )
        return body

    def _http_error_message(self, e: urllib.error.HTTPError, path: str) -> str:
        if e.code == 401:
            return (
                f"{self.address} refused the request as unauthenticated (401). The "
                "API password is wrong, or the session expired mid-run."
            )
        if e.code == 404:
            return (
                f"{self.address} has no {path} endpoint (404). Pi-hole v5 does not "
                "expose the v6 REST API — labops needs Pi-hole v6."
            )
        # Pi-hole puts a human-readable reason in the error body; use it when it is
        # there, since "HTTP 400" alone says nothing actionable.
        detail: str = ""
        try:
            body: object = json.loads(e.read())
            if isinstance(body, dict):
                error: object = body.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or "")
        except Exception:
            pass
        suffix: str = f": {detail}" if detail else ""
        return f"{self.address} returned HTTP {e.code} for {path}{suffix}"
