"""Tests for src/cli/update.py — selector resolution, preview, and fan-out.

Ansible is never invoked: the three phase entry points are monkeypatched with
stubs that append to a call log, so these assert on *which* phases ran with
*which* targets. ``update`` is a plain command on the root app (not a sub-app),
so it is wrapped in a throwaway Typer here to be invocable on its own.
"""

import importlib
from types import ModuleType
from typing import Any, Optional

import pytest
import typer
from typer.testing import CliRunner

from models.input_conf.yaml_root import YamlRoot
from src.cli.core import state
from src.utils.ansible_runner import RunSummary

_update_module: ModuleType = importlib.import_module("src.cli.update")

app = typer.Typer()
app.command()(_update_module.update)
runner = CliRunner()


# ─── Fixtures ─────────────────────────────────────────────────────────────────


def _ok() -> RunSummary:
    return RunSummary(rc=0, unreachable={}, failed={}, ok={}, raw_tail="")


def _failed() -> RunSummary:
    return RunSummary(rc=2, unreachable={}, failed={"h": "boom"}, ok={}, raw_tail="")


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str]]]:
    """Replace the three phase runners with stubs recording (phase, targets)."""
    log: list[tuple[str, list[str]]] = []

    def _hosts(nodes: list[Any], *a: object, **kw: object) -> Optional[RunSummary]:
        log.append(("ssh", [n.name for n in nodes]))
        return _ok()

    def _lxcs(pairs: list[Any], *a: object, **kw: object) -> Optional[RunSummary]:
        log.append(("lxc", [lxc.name for _, lxc in pairs]))
        return _ok()

    def _stacks(stacks: list[Any], creds: object) -> RunSummary:
        log.append(("docker", [s.stack.name for s in stacks]))
        return _ok()

    monkeypatch.setattr(_update_module.host, "update", _hosts)
    monkeypatch.setattr(_update_module.lxc, "update", _lxcs)
    monkeypatch.setattr(_update_module, "_run_stacks", _stacks)
    return log


@pytest.fixture(autouse=True)
def loaded_config(valid_config_dict: dict[str, Any]) -> dict[str, Any]:
    """Seed the module-global state the command reads its config from."""
    valid_config_dict["hosts"]["prox"]["tags"] = ["prod"]
    valid_config_dict["hosts"]["prox"]["vm"]["vm1"]["tags"] = ["media"]
    valid_config_dict["settings"]["targets"] = {
        "weekly": {"kind": ["vm", "lxc"]},
        "boxes": {"kind": ["host"]},
    }
    state.model = YamlRoot.model_validate(valid_config_dict)
    state.dry_run = False
    state.verbose = False
    return valid_config_dict


# ─── Fan-out ──────────────────────────────────────────────────────────────────


def test_all_runs_every_phase_in_order(calls: list[tuple[str, list[str]]]) -> None:
    result = runner.invoke(app, ["--all", "--yes"])
    assert result.exit_code == 0
    assert [phase for phase, _ in calls] == ["ssh", "lxc", "docker"]


def test_kind_lxc_skips_the_ssh_phase(calls: list[tuple[str, list[str]]]) -> None:
    result = runner.invoke(app, ["--kind", "lxc", "--yes"])
    assert result.exit_code == 0
    assert dict(calls) == {"lxc": ["ct1"]}


def test_kind_host_skips_lxc_and_docker(calls: list[tuple[str, list[str]]]) -> None:
    # The three hosts carry no docker stacks, so only the SSH phase has work.
    result = runner.invoke(app, ["--kind", "host", "--yes"])
    assert result.exit_code == 0
    assert [phase for phase, _ in calls] == ["ssh"]


def test_only_stacks_runs_docker_alone(calls: list[tuple[str, list[str]]]) -> None:
    result = runner.invoke(app, ["--all", "--only", "stacks", "--yes"])
    assert result.exit_code == 0
    assert dict(calls) == {"docker": ["app"]}


def test_only_nodes_never_touches_docker(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--all", "--only", "nodes", "--yes"])
    assert result.exit_code == 0
    assert "docker" not in dict(calls)


def test_under_selects_a_subtree(calls: list[tuple[str, list[str]]]) -> None:
    result = runner.invoke(app, ["--under", "prox", "--yes"])
    assert result.exit_code == 0
    assert dict(calls)["ssh"] == ["prox", "vm1"]
    assert dict(calls)["lxc"] == ["ct1"]


def test_tag_selects_the_tagged_node(calls: list[tuple[str, list[str]]]) -> None:
    result = runner.invoke(app, ["--tag", "media", "--yes"])
    assert result.exit_code == 0
    assert dict(calls)["ssh"] == ["vm1"]


def test_named_set_buckets_like_the_equivalent_flags(
    calls: list[tuple[str, list[str]]],
) -> None:
    runner.invoke(app, ["weekly", "--yes"])
    from_set = list(calls)
    calls.clear()
    runner.invoke(app, ["--kind", "vm", "--kind", "lxc", "--yes"])
    assert from_set == list(calls)


# ─── Exit codes ───────────────────────────────────────────────────────────────


def test_a_failing_phase_fails_the_command(
    monkeypatch: pytest.MonkeyPatch, calls: list[tuple[str, list[str]]]
) -> None:
    monkeypatch.setattr(_update_module.lxc, "update", lambda *a, **kw: _failed())
    result = runner.invoke(app, ["--all", "--yes"])
    assert result.exit_code == 1
    assert "phase(s) completed" in result.output


def test_all_phases_succeeding_exits_zero(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--all", "--yes"])
    assert result.exit_code == 0
    assert "All 3 phase(s) completed" in result.output


# ─── Preview and confirmation ─────────────────────────────────────────────────


def test_list_previews_and_runs_nothing(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--all", "--list"])
    assert result.exit_code == 0
    assert calls == []
    assert "prox" in result.output


def test_declining_the_prompt_runs_nothing(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--all"], input="n\n")
    assert result.exit_code != 0
    assert calls == []


def test_confirming_the_prompt_runs_the_phases(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--all"], input="y\n")
    assert result.exit_code == 0
    assert calls != []


def test_dry_run_skips_the_prompt(calls: list[tuple[str, list[str]]]) -> None:
    state.dry_run = True
    try:
        result = runner.invoke(app, ["--all"])
        assert result.exit_code == 0
        assert calls != []
    finally:
        state.dry_run = False


def test_single_target_needs_no_confirmation(
    calls: list[tuple[str, list[str]]],
) -> None:
    # ct1 alone: one node, no stacks — nothing to double-check.
    result = runner.invoke(app, ["--under", "ct1"])
    assert result.exit_code == 0
    assert dict(calls) == {"lxc": ["ct1"]}


# ─── Errors ───────────────────────────────────────────────────────────────────


def test_no_selector_and_no_all_exits_one(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 1
    assert "Nothing selected" in result.output
    assert calls == []


def test_named_set_plus_options_is_refused(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["weekly", "--tag", "prod"])
    assert result.exit_code == 1
    assert "not both" in result.output
    assert calls == []


def test_unknown_set_lists_the_defined_ones(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["nightly"])
    assert result.exit_code == 1
    assert "No target set named 'nightly'" in result.output
    assert "boxes, weekly" in result.output


def test_a_node_name_as_a_set_suggests_under(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["prox"])
    assert result.exit_code == 1
    assert "--under prox" in result.output


def test_unknown_under_name_exits_one_without_a_traceback(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--under", "nope"])
    assert result.exit_code == 1
    assert "nope" in result.output
    assert "Traceback" not in result.output
    assert calls == []


def test_empty_match_exits_one(calls: list[tuple[str, list[str]]]) -> None:
    result = runner.invoke(app, ["--kind", "vm", "--os", "alpine"])
    assert result.exit_code == 1
    assert "Nothing matched" in result.output
    assert calls == []


def test_invalid_kind_is_rejected_by_the_choice(
    calls: list[tuple[str, list[str]]],
) -> None:
    result = runner.invoke(app, ["--kind", "container"])
    assert result.exit_code != 0
    assert calls == []
