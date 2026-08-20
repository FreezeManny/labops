"""Tests for src/dns/sync.py and the backend layer above it.

``plan_sync`` is deliberately tiny — read, then diff — so what is worth pinning is
the seam it sits on: that a plan is computed against the state it was read from,
that unreadable entries survive the trip into the plan, and that resolving *which*
server to talk to happens in one place and fails before the first request.

The diff itself is test_diff.py; the password and the wire are tests/dns/pihole/.
"""

from pathlib import Path
from typing import Any, Optional

import pytest

from models.dns.record import DnsPlan, DnsRecord, LiveRecord
from models.input_conf.yaml_root import YamlRoot
from src.dns import DnsBackend, dns_warnings, plan_sync, require_dns, resolve_backend
from src.dns.pihole import PiholeBackend


def _model(cfg: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(cfg)


def _record(hostname: str, ip: str) -> DnsRecord:
    from ipaddress import IPv4Address

    return DnsRecord(hostname=hostname, ip=IPv4Address(ip), path=["node"])


def _live(hostname: str, ip: str) -> LiveRecord:
    from ipaddress import IPv4Address

    return LiveRecord(hostname=hostname, ip=IPv4Address(ip))


class _Backend:
    """A DNS server that holds whatever it was handed. Never touches a network."""

    name = "Fake"

    def __init__(
        self,
        current: Optional[list[LiveRecord]] = None,
        unparsed: Optional[list[str]] = None,
    ) -> None:
        self._current = current or []
        self._unparsed = unparsed or []
        self.applied: Optional[list[DnsRecord]] = None
        self.reads = 0

    @property
    def where(self) -> str:
        return "nowhere in particular"

    def read(self) -> tuple[list[LiveRecord], list[str]]:
        self.reads += 1
        return self._current, self._unparsed

    def apply(self, desired: list[DnsRecord]) -> None:
        self.applied = desired


# ── the protocol ──────────────────────────────────────────────────────────────


def test_four_members_are_all_a_backend_needs() -> None:
    """Pinned structurally: a server with no session, port or password still fits."""
    assert isinstance(_Backend(), DnsBackend)


# ── plan_sync ─────────────────────────────────────────────────────────────────


def test_a_plan_is_the_config_diffed_against_what_was_read() -> None:
    backend = _Backend(current=[_live("old.lab", "10.0.0.9")])
    plan: DnsPlan = plan_sync(backend, [_record("nas.lab", "10.0.0.5")])

    assert [r.hostname for r in plan.add] == ["nas.lab"]
    assert [r.hostname for r in plan.remove] == ["old.lab"]
    assert backend.reads == 1


def test_planning_changes_nothing() -> None:
    """`dns diff` and the first half of `dns sync` must both be safe to run."""
    backend = _Backend(current=[_live("nas.lab", "10.0.0.5")])
    plan_sync(backend, [_record("nas.lab", "10.0.0.5")])
    assert backend.applied is None


def test_unreadable_entries_reach_the_plan_rather_than_the_log() -> None:
    """A sync rewrites the whole array, so they are a deletion like any other."""
    backend = _Backend(unparsed=["fd00::1 v6.lab"])
    plan = plan_sync(backend, [])
    assert plan.unparsed == ["fd00::1 v6.lab"]
    assert plan.has_deletions


def test_a_server_already_matching_the_config_plans_nothing() -> None:
    backend = _Backend(current=[_live("nas.lab", "10.0.0.5")])
    plan = plan_sync(backend, [_record("nas.lab", "10.0.0.5")])
    assert not plan.has_changes
    assert [r.hostname for r in plan.unchanged] == ["nas.lab"]


# ── require_dns ───────────────────────────────────────────────────────────────


def test_require_dns_returns_the_block(dns_config_dict: dict[str, Any]) -> None:
    assert require_dns(_model(dns_config_dict)).suffix == "lab"


def test_require_dns_names_what_is_missing(valid_config_dict: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="settings.dns is not configured"):
        require_dns(_model(valid_config_dict))


# ── resolve_backend ───────────────────────────────────────────────────────────


def test_a_pihole_block_resolves_to_the_pihole_backend(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    (tmp_path / ".env").write_text("PIHOLE_PASSWORD=secret\n")
    backend = resolve_backend(_model(dns_config_dict), tmp_path / "homelab.yml")
    assert isinstance(backend, PiholeBackend)
    assert backend.name == "Pi-hole"


def test_a_suffix_with_no_server_says_records_are_still_derived(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    valid_config_dict["settings"]["dns"] = {"suffix": ".lab"}
    with pytest.raises(ValueError, match="names no DNS server"):
        resolve_backend(_model(valid_config_dict), tmp_path / "homelab.yml")


def test_resolving_a_backend_fails_before_the_first_request(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    """No password anywhere: the failure belongs here, not halfway through a sync."""
    with pytest.raises(ValueError, match="no Pi-hole API password found"):
        resolve_backend(_model(dns_config_dict), tmp_path / "homelab.yml")


# ── dns_warnings ──────────────────────────────────────────────────────────────


def test_warnings_are_asked_before_a_backend_is_built(
    dns_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    """No password is configured, so building one would fail — warnings still work."""
    dns_config_dict["settings"]["dns"]["pihole"]["password"] = "inline"
    warnings = dns_warnings(_model(dns_config_dict), tmp_path / "homelab.yml")
    assert any("clear text" in w for w in warnings)


def test_no_dns_block_warns_about_nothing(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    assert dns_warnings(_model(valid_config_dict), tmp_path / "homelab.yml") == []


def test_no_server_block_warns_about_nothing(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    valid_config_dict["settings"]["dns"] = {"suffix": ".lab"}
    assert dns_warnings(_model(valid_config_dict), tmp_path / "homelab.yml") == []
