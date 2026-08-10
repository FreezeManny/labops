"""Tests for src/cli/wake.py — which of the three wake paths a target takes.

One verb hides three mechanisms, and picking between them automatically is the
whole point of the command, so most of these assert on *which* one ran: a local
UDP broadcast, a relayed one (``--via``), or ``qm``/``pct start`` on the parent.
Nothing is sent and no playbook runs — the three entry points are monkeypatched
with recorders.

``wake`` is a plain command on the root app (not a sub-app), so it is wrapped in
a throwaway Typer here to be invocable on its own — same as
tests/src/test_cli_update.py.

In ``wake_config_dict``: ``nas`` (bare-metal, has a mac), ``ct1`` (lxc, has a
mac), ``vm1`` (vm, no mac), ``edge`` (bare-metal, no mac).
"""

import importlib
from types import ModuleType, SimpleNamespace
from typing import Any, Optional

import pytest
import typer
from click.testing import Result
from typer.testing import CliRunner

from models.input_conf.yaml_root import YamlRoot
from models.tree import NodeRef
from src.cli.core import state

_module: ModuleType = importlib.import_module("src.cli.wake")

app = typer.Typer()
app.command()(_module.wake)
runner = CliRunner()

NAS_MAC = "aa:bb:cc:dd:ee:01"
CT1_MAC = "aa:bb:cc:dd:ee:02"


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def loaded_config(wake_config_dict: dict[str, Any]) -> YamlRoot:
    """Seed the module-global state the command reads its config from."""
    model = YamlRoot.model_validate(wake_config_dict)
    state.model = model
    state.dry_run = False
    state.verbose = False
    return model


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Replace the three wake paths with recorders of (path, arguments)."""
    log: list[tuple[str, Any]] = []

    def _packet(mac: str, broadcast: str, port: int) -> None:
        log.append(("packet", (mac, broadcast, port)))

    def _via(
        config: object,
        mac: str,
        via: str,
        broadcast: str,
        port: int,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> SimpleNamespace:
        log.append(("via", (mac, via, broadcast, port, dry_run)))
        return SimpleNamespace(rc=0)

    def _guest(
        config: object, ref: NodeRef, dry_run: bool = False, verbose: bool = False
    ) -> SimpleNamespace:
        log.append(("guest", (ref.node.name, dry_run)))
        return SimpleNamespace(rc=0)

    monkeypatch.setattr(_module, "send_magic_packet", _packet)
    monkeypatch.setattr(_module, "send_via", _via)
    monkeypatch.setattr(_module, "start_guest", _guest)
    return log


def _paths(calls: list[tuple[str, Any]]) -> list[str]:
    return [path for path, _ in calls]


def _out(result: Result) -> str:
    """Output with wrapping collapsed — rich breaks lines at the terminal width."""
    return " ".join(result.output.split())


# ─── Path selection ───────────────────────────────────────────────────────────


def test_a_bare_metal_host_gets_a_local_packet(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["nas"])
    assert result.exit_code == 0
    assert calls == [("packet", (NAS_MAC, "255.255.255.255", 9))]


def test_a_guest_is_started_on_its_parent(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["ct1"])
    assert result.exit_code == 0
    assert calls == [("guest", ("ct1", False))]


def test_a_guest_with_packet_gets_a_packet_instead(
    calls: list[tuple[str, Any]],
) -> None:
    result = runner.invoke(app, ["ct1", "--packet"])
    assert result.exit_code == 0
    assert calls == [("packet", (CT1_MAC, "255.255.255.255", 9))]


def test_via_relays_the_packet(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["nas", "--via", "edge"])
    assert result.exit_code == 0
    assert calls == [("via", (NAS_MAC, "edge", "255.255.255.255", 9, False))]


def test_via_implies_packet_for_a_guest(calls: list[tuple[str, Any]]) -> None:
    """Documented in --via's help: it never falls through to qm/pct start."""
    result = runner.invoke(app, ["ct1", "--via", "edge"])
    assert result.exit_code == 0
    assert _paths(calls) == ["via"]


def test_packet_on_a_host_is_a_no_op_flag(calls: list[tuple[str, Any]]) -> None:
    """A host has no parent to start it from, so --packet changes nothing."""
    runner.invoke(app, ["nas", "--packet"])
    assert _paths(calls) == ["packet"]


def test_a_target_can_be_given_by_vmid(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["101"])
    assert result.exit_code == 0
    assert calls == [("guest", ("ct1", False))]


def test_a_target_can_be_given_by_ip(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["10.0.0.5"])
    assert result.exit_code == 0
    assert _paths(calls) == ["packet"]


def test_broadcast_and_port_reach_the_local_path(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["nas", "-b", "10.0.0.255", "-p", "7"])
    assert result.exit_code == 0
    assert calls == [("packet", (NAS_MAC, "10.0.0.255", 7))]


def test_broadcast_and_port_reach_the_relay(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["nas", "--via", "edge", "-b", "10.0.0.255", "-p", "7"])
    assert result.exit_code == 0
    assert calls[0][1][2:4] == ("10.0.0.255", 7)


# ─── Which path ran is always printed ─────────────────────────────────────────


def test_the_local_path_names_the_mac_and_destination(
    calls: list[tuple[str, Any]],
) -> None:
    result = runner.invoke(app, ["nas"])
    assert NAS_MAC in _out(result)
    assert "255.255.255.255:9" in _out(result)
    assert "from this machine" in _out(result)


def test_the_relay_path_names_the_relay(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["nas", "--via", "edge"])
    assert "via edge" in _out(result)


def test_the_guest_path_names_the_cli_and_the_parent(
    calls: list[tuple[str, Any]],
) -> None:
    result = runner.invoke(app, ["ct1"])
    assert "pct start" in _out(result)
    assert "prox" in _out(result)


def test_a_vm_reports_qm_rather_than_pct(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["vm1"])
    assert "qm start" in _out(result)


# ─── Dry run ──────────────────────────────────────────────────────────────────


def test_dry_run_sends_no_packet(calls: list[tuple[str, Any]]) -> None:
    """The local path has no ansible --check to fall back on, so it returns early."""
    state.dry_run = True
    result = runner.invoke(app, ["nas"])

    assert result.exit_code == 0
    assert calls == []
    assert "no packet was sent" in _out(result)


def test_dry_run_still_runs_the_playbook_paths_in_check_mode(
    calls: list[tuple[str, Any]],
) -> None:
    state.dry_run = True
    runner.invoke(app, ["ct1"])
    assert calls == [("guest", ("ct1", True))]


def test_dry_run_reaches_the_relay_as_check(calls: list[tuple[str, Any]]) -> None:
    state.dry_run = True
    runner.invoke(app, ["nas", "--via", "edge"])
    assert calls[0][1][-1] is True


# ─── --wait ───────────────────────────────────────────────────────────────────


@pytest.fixture
def waited(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int, float]]:
    log: list[tuple[str, int, float]] = []

    def _wait(ip: str, port: int, timeout: float) -> Optional[float]:
        log.append((ip, port, timeout))
        return 12.0

    monkeypatch.setattr(_module, "wait_until_up", _wait)
    return log


def test_no_wait_by_default(
    calls: list[tuple[str, Any]], waited: list[tuple[str, int, float]]
) -> None:
    runner.invoke(app, ["nas"])
    assert waited == []


def test_wait_polls_the_woken_nodes_ip(
    calls: list[tuple[str, Any]], waited: list[tuple[str, int, float]]
) -> None:
    result = runner.invoke(app, ["nas", "--wait", "60"])
    assert result.exit_code == 0
    assert waited == [("10.0.0.5", 22, 60.0)]
    assert "is up" in _out(result)


def test_wait_port_is_honoured(
    calls: list[tuple[str, Any]], waited: list[tuple[str, int, float]]
) -> None:
    runner.invoke(app, ["nas", "--wait", "60", "--wait-port", "8006"])
    assert waited[0][1] == 8006


def test_a_node_that_never_answers_fails_the_command(
    calls: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The packet went out fine; the machine did not come up. That is not a success."""
    monkeypatch.setattr(_module, "wait_until_up", lambda *a, **kw: None)

    result = runner.invoke(app, ["nas", "--wait", "60"])

    assert result.exit_code == 1
    assert "did not answer" in _out(result)
    assert _paths(calls) == ["packet"]  # it was still woken


def test_wait_is_skipped_in_a_dry_run(
    calls: list[tuple[str, Any]], waited: list[tuple[str, int, float]]
) -> None:
    state.dry_run = True
    result = runner.invoke(app, ["nas", "--wait", "60"])

    assert result.exit_code == 0
    assert waited == []


def test_wait_follows_the_guest_path_too(
    calls: list[tuple[str, Any]], waited: list[tuple[str, int, float]]
) -> None:
    runner.invoke(app, ["ct1", "--wait", "60"])
    assert _paths(calls) == ["guest"]
    assert waited == [("10.0.0.2", 22, 60.0)]


# ─── --list ───────────────────────────────────────────────────────────────────


def test_list_shows_the_nodes_with_a_mac_and_wakes_nothing(
    calls: list[tuple[str, Any]],
) -> None:
    result = runner.invoke(app, ["--list"])

    assert result.exit_code == 0
    assert calls == []
    assert "ct1" in _out(result) and "nas" in _out(result)
    assert "edge" not in _out(result)  # no mac


def test_list_wins_over_a_target(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["nas", "--list"])
    assert result.exit_code == 0
    assert calls == []


def test_list_says_so_when_no_node_has_a_mac(
    wake_config_dict: dict[str, Any], calls: list[tuple[str, Any]]
) -> None:
    del wake_config_dict["hosts"]["nas"]["mac"]
    del wake_config_dict["hosts"]["prox"]["lxc"]["ct1"]["mac"]
    state.model = YamlRoot.model_validate(wake_config_dict)
    result = runner.invoke(app, ["--list"])

    assert result.exit_code == 0
    assert "No node has a 'mac'" in _out(result)


# ─── Errors ───────────────────────────────────────────────────────────────────


def test_no_target_and_no_list_exits_one(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "Give a node to wake" in _out(result)
    assert calls == []


def test_an_unknown_target_exits_one_without_a_traceback(
    calls: list[tuple[str, Any]],
) -> None:
    result = runner.invoke(app, ["nope"])
    assert result.exit_code == 1
    assert "nope" in _out(result)
    assert "Traceback" not in _out(result)
    assert calls == []


def test_a_host_without_a_mac_says_what_to_add(calls: list[tuple[str, Any]]) -> None:
    result = runner.invoke(app, ["edge"])

    assert result.exit_code == 1
    assert "has no 'mac'" in _out(result)
    assert "--list" in _out(result)  # how to see the ones that do
    assert calls == []


def test_packet_on_a_guest_without_a_mac_is_refused(
    calls: list[tuple[str, Any]],
) -> None:
    """vm1 would start happily without --packet; asking for one it cannot use fails."""
    result = runner.invoke(app, ["vm1", "--packet"])

    assert result.exit_code == 1
    assert "has no 'mac'" in _out(result)
    assert calls == []


def test_a_failing_playbook_fails_the_command(
    calls: list[tuple[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        _module,
        "start_guest",
        lambda *a, **kw: SimpleNamespace(
            rc=2, stats={"failures": {"wake_parent_prox": 1}}, events=[]
        ),
    )

    result = runner.invoke(app, ["ct1"])
    assert result.exit_code == 1


def test_an_unresolvable_via_exits_one_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The relay is only resolved once the playbook path runs, so it lands late."""

    def _boom(*a: object, **kw: object) -> None:
        raise ValueError("--via 'nope' matches no host, VM or LXC in the config")

    monkeypatch.setattr(_module, "send_via", _boom)

    result = runner.invoke(app, ["nas", "--via", "nope"])

    assert result.exit_code == 1
    assert "nope" in _out(result)
    assert "Traceback" not in _out(result)
