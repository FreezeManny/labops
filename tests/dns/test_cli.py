"""Tests for the `dns list` / `diff` / `sync` commands.

Two things are being pinned down here. First, that every expected failure reads as
a one-line message rather than a traceback — same contract as
tests/proxy/test_deploy_cli.py. Second, the sync guard rail: a plan that deletes
must not be applied without consent, since labops owns the record list outright.

``plan_sync`` / ``apply_sync`` are stubbed, so nothing here touches a network.
"""

from ipaddress import IPv4Address
from pathlib import Path
from typing import Any, Optional

import pytest
from typer.testing import CliRunner

from models.dns.record import DnsPlan, DnsRecord, LiveRecord
from models.input_conf.dns import Dns
from models.input_conf.yaml_root import YamlRoot
from src.cli import dns as dns_cli
from src.cli.core import state
from src.dns import PiholeError

runner = CliRunner()
app = dns_cli.app


@pytest.fixture(autouse=True)
def _reset_state(tmp_path: Path) -> None:
    """Point the CLI at a config dir with a usable secret store, and clear --dry-run.

    ``state`` is module-level, so a leaked dry_run from one test would silently
    disarm the next one's apply.
    """
    (tmp_path / ".env").write_text("PIHOLE_PASSWORD=secret\n")
    state.config_path = tmp_path / "homelab.yml"
    state.dry_run = False


def _load(cfg: dict[str, Any]) -> None:
    state.model = YamlRoot.model_validate(cfg)


def _plan(
    add: Optional[list[tuple[str, str]]] = None,
    remove: Optional[list[tuple[str, str]]] = None,
    unchanged: int = 0,
    unparsed: Optional[list[str]] = None,
) -> DnsPlan:
    return DnsPlan(
        add=[
            DnsRecord(hostname=h, ip=IPv4Address(ip), path=[h]) for h, ip in (add or [])
        ],
        update=[],
        remove=[LiveRecord(hostname=h, ip=IPv4Address(ip)) for h, ip in (remove or [])],
        unchanged=[
            DnsRecord(hostname=f"same{n}.lab", ip=IPv4Address("10.0.0.1"), path=[])
            for n in range(unchanged)
        ],
        unparsed=list(unparsed or []),
    )


def _stub_plan(monkeypatch: pytest.MonkeyPatch, plan: DnsPlan) -> None:
    def _fake(config: YamlRoot, password: str, desired: list[DnsRecord]) -> DnsPlan:
        return plan

    monkeypatch.setattr(dns_cli, "plan_sync", _fake)


def _stub_apply(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record the location each write went to."""
    applied: list[str] = []

    def _fake(config: YamlRoot, password: str, desired: list[DnsRecord]) -> None:
        assert config.settings.dns is not None
        location = config.settings.dns.pihole_location
        assert location is not None  # sync cannot get here without one
        applied.append(location)

    monkeypatch.setattr(dns_cli, "apply_sync", _fake)
    return applied


# ─── dns list ─────────────────────────────────────────────────────────────────


def test_list_renders_derived_records(dns_config_dict: dict[str, Any]) -> None:
    _load(dns_config_dict)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "nas.lab" in result.output
    assert "10.0.0.5" in result.output


def test_list_needs_no_password(dns_config_dict: dict[str, Any]) -> None:
    # Derivation is offline, so a missing secret store must not block it.
    assert state.config_path is not None
    (state.config_path.parent / ".env").unlink()
    _load(dns_config_dict)
    assert runner.invoke(app, ["list"]).exit_code == 0


def test_list_without_dns_settings_exits_cleanly(
    valid_config_dict: dict[str, Any],
) -> None:
    _load(valid_config_dict)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 1
    assert "settings.dns is not configured" in result.output
    assert "Traceback" not in result.output


def test_list_with_everything_opted_out(dns_config_dict: dict[str, Any]) -> None:
    for host in dns_config_dict["hosts"].values():
        host["dns"] = False
        for child in list(host.get("lxc", {}).values()) + list(
            host.get("vm", {}).values()
        ):
            child["dns"] = False
    _load(dns_config_dict)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No DNS records derived" in result.output


# ─── missing password ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("command", ["diff", "sync"])
def test_missing_password_exits_cleanly(
    command: str, dns_config_dict: dict[str, Any]
) -> None:
    assert state.config_path is not None
    (state.config_path.parent / ".env").unlink()
    _load(dns_config_dict)
    result = runner.invoke(app, [command])
    assert result.exit_code == 1
    assert "PIHOLE_PASSWORD is not set" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize("command", ["diff", "sync"])
def test_unreachable_pihole_exits_cleanly(
    command: str, dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_: object, **__: object) -> DnsPlan:
        raise PiholeError("could not reach the Pi-hole API at http://x: refused")

    monkeypatch.setattr(dns_cli, "plan_sync", _boom)
    _load(dns_config_dict)
    result = runner.invoke(app, [command])
    assert result.exit_code == 1
    assert "could not reach" in result.output
    assert "Traceback" not in result.output


# ─── dns diff ─────────────────────────────────────────────────────────────────


def test_diff_prints_the_plan(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(add=[("new.lab", "10.0.0.9")], unchanged=3))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["diff"])
    assert result.exit_code == 0
    assert "new.lab" in result.output
    assert "3 unchanged" in result.output
    assert applied == []  # diff never writes


def test_diff_reports_a_match(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(unchanged=5))
    _load(dns_config_dict)
    result = runner.invoke(app, ["diff"])
    assert "already matches the config" in result.output


# ─── dns sync ─────────────────────────────────────────────────────────────────


def test_sync_applies_additions_without_prompting(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(add=[("new.lab", "10.0.0.9")]))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert applied == ["10.0.0.53"]


def test_sync_prompts_before_deleting(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(remove=[("stale.lab", "10.0.0.99")]))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"], input="n\n")
    assert result.exit_code == 1
    assert "1 record(s) will be deleted" in result.output
    assert applied == []  # declined -> nothing written


def test_sync_deletes_when_confirmed(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(remove=[("stale.lab", "10.0.0.99")]))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"], input="y\n")
    assert result.exit_code == 0
    assert applied == ["10.0.0.53"]


def test_sync_yes_skips_the_prompt(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(remove=[("stale.lab", "10.0.0.99")]))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync", "--yes"])
    assert result.exit_code == 0
    assert applied == ["10.0.0.53"]
    assert "Continue?" not in result.output


def test_dry_run_writes_nothing(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(add=[("new.lab", "10.0.0.9")]))
    applied = _stub_apply(monkeypatch)
    state.dry_run = True
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "nothing was written" in result.output
    assert applied == []


def test_sync_with_no_changes_writes_nothing(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(unchanged=4))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "already matches" in result.output
    assert applied == []


def test_apply_failure_exits_cleanly(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The plan read fine and the Pi-hole died before the write — still a one-line
    # message, not a traceback.
    _stub_plan(monkeypatch, _plan(add=[("new.lab", "10.0.0.9")]))

    def _fake_apply(config: YamlRoot, password: str, desired: list[DnsRecord]) -> None:
        raise PiholeError("connection refused")

    monkeypatch.setattr(dns_cli, "apply_sync", _fake_apply)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "connection refused" in result.output
    assert "Traceback" not in result.output


def test_inline_password_warning_is_shown(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    dns_config_dict["settings"]["dns"]["password"] = "inline"
    _stub_plan(monkeypatch, _plan(unchanged=1))
    _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"])
    assert "clear text" in result.output


def test_unparsed_records_are_surfaced(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(monkeypatch, _plan(unchanged=1, unparsed=["fe80::1 v6.lab"]))
    _load(dns_config_dict)
    result = runner.invoke(app, ["diff"])
    assert "cannot read" in result.output
    assert "fe80::1 v6.lab" in result.output


def test_unparsed_records_alone_still_prompt(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nothing to add, update or remove — but the write drops the unreadable line, so
    # it is a destructive change and must ask first.
    _stub_plan(monkeypatch, _plan(unchanged=1, unparsed=["fe80::1 v6.lab"]))
    applied = _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync"], input="n\n")
    assert result.exit_code == 1
    assert "1 record(s) will be deleted" in result.output
    assert applied == []


def test_unparsed_records_counted_in_the_summary(
    dns_config_dict: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_plan(
        monkeypatch,
        _plan(remove=[("stale.lab", "10.0.0.99")], unparsed=["fe80::1 v6.lab"]),
    )
    _stub_apply(monkeypatch)
    _load(dns_config_dict)
    result = runner.invoke(app, ["sync", "--yes"])
    assert result.exit_code == 0
    assert "2 removed" in result.output


# ─── dns upgrade ──────────────────────────────────────────────────────────────
#
# The one command that does not touch the API. These never reach Ansible: the
# config checks and target resolution fail first, which is what a typo produces.


def test_upgrade_without_dns_settings_exits_cleanly(
    valid_config_dict: dict[str, Any],
) -> None:
    _load(valid_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "settings.dns is not configured" in result.output
    assert "Traceback" not in result.output


def test_upgrade_needs_no_api_password(dns_config_dict: dict[str, Any]) -> None:
    # Upgrading goes over SSH, so a missing PIHOLE_PASSWORD must not block it — the
    # failure below is target resolution, not credentials.
    assert state.config_path is not None
    (state.config_path.parent / ".env").unlink()
    dns_config_dict["settings"]["dns"]["pihole_location"] = "nope"
    _load(dns_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "PIHOLE_PASSWORD" not in result.output
    # Short fragment: rich wraps the full sentence across lines.
    assert "matches no host" in result.output


def test_upgrade_of_an_off_config_ip_exits_cleanly(
    dns_config_dict: dict[str, Any],
) -> None:
    # The fixture's location is a bare IP naming no node: records work, upgrading
    # cannot, and the message has to distinguish the two.
    _load(dns_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "is an address, not a node" in result.output
    assert "Traceback" not in result.output


def test_upgrade_of_a_docker_stack_exits_cleanly(
    dns_config_dict: dict[str, Any],
) -> None:
    dns_config_dict["settings"]["dns"]["pihole_location"] = "app"  # a stack
    _load(dns_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "is a docker stack" in result.output
    assert "docker stack --stack app update" in result.output
    assert "Traceback" not in result.output


def test_upgrade_of_an_unmanaged_node_exits_cleanly(
    dns_config_dict: dict[str, Any],
) -> None:
    dns_config_dict["settings"]["dns"]["pihole_location"] = "nas"  # os: unmanaged
    _load(dns_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "os: unmanaged" in result.output
    assert "Traceback" not in result.output


def test_upgrade_ambiguous_location_exits_cleanly(
    dns_config_dict: dict[str, Any],
) -> None:
    # A name that is both a node and a docker stack: legal config, and the one
    # ambiguity still reachable now that names and IPs are unique tree-wide.
    dns_config_dict["hosts"]["app"] = {
        "type": "bare-metal",
        "os": "debian",
        "ip": "10.0.0.7",
    }
    dns_config_dict["settings"]["dns"]["pihole_location"] = "app"
    _load(dns_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    assert "ambiguous" in result.output
    assert "Traceback" not in result.output


def test_upgrade_of_a_vmid_location_exits_cleanly(
    dns_config_dict: dict[str, Any],
) -> None:
    """A vmid is not a node id, and saying so must not read as a traceback."""
    dns_config_dict["settings"]["dns"]["pihole_location"] = "101"  # ct1's vmid
    _load(dns_config_dict)
    result = runner.invoke(app, ["upgrade"])
    assert result.exit_code == 1
    # Fragments only: typer hard-wraps the rendered error mid-sentence.
    assert "matches no host, VM, LXC or docker" in result.output
    assert "is not an IP address" in result.output
    assert "Traceback" not in result.output


# ─── pihole_location left unset ───────────────────────────────────────────────
#
# Optional, so `dns list` must keep working while everything that talks to a
# Pi-hole explains what is missing.


def test_list_works_without_a_pihole_location(
    dns_config_dict: dict[str, Any],
) -> None:
    del dns_config_dict["settings"]["dns"]["pihole_location"]
    _load(dns_config_dict)
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "nas.lab" in result.output


@pytest.mark.parametrize("command", ["diff", "sync", "upgrade"])
def test_unset_location_exits_cleanly(
    command: str, dns_config_dict: dict[str, Any]
) -> None:
    del dns_config_dict["settings"]["dns"]["pihole_location"]
    _load(dns_config_dict)
    result = runner.invoke(app, [command])
    assert result.exit_code == 1
    assert "is not set" in result.output
    assert "Traceback" not in result.output
