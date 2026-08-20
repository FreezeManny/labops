"""Tests for `name` as an override, on all three node kinds.

The key a node is written under is its name — unless the node sets `name:`, which
replaces it. `models/nodes.py` (``node_matches``) is where that is decided: a node
that overrode its name is *no longer reachable by its key*, because one node
answering to two identifiers is what the field exists to avoid.

Two halves are pinned here, because it is the pair that has to agree:

* what a node is addressable *as* — the model side; and
* what the listings *print* — which is where you read off the thing to type.

`host list` and `vm list` used to print the dict key while `lxc list` printed the
effective name, so a renamed host was listed under an identifier that every
command rejected.
"""

from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from models.input_conf.yaml_root import YamlRoot
from models.nodes import NodeNotFound
from src.cli.core import state
import src.cli.host as host_cli
import src.cli.vm as vm_cli

runner = CliRunner()


@pytest.fixture
def renamed(valid_config_dict: dict[str, Any]) -> YamlRoot:
    """`edge` written under a key that is not a legal DNS label, plus a renamed VM.

    This is the case the field is for: the key stays whatever the config author
    wanted to file it under, and `name` is the addressable, publishable one.
    """
    hosts: dict[str, Any] = valid_config_dict["hosts"]
    hosts["edge_box_01"] = {**hosts.pop("edge"), "name": "edge"}
    valid_config_dict["hosts"]["prox"]["vm"]["vm1"]["name"] = "media"
    return YamlRoot.model_validate(valid_config_dict)


# ── Addressing ────────────────────────────────────────────────────────────────


def test_a_renamed_host_resolves_by_its_name(renamed: YamlRoot) -> None:
    assert renamed.find_node("edge").node.name == "edge"


def test_a_renamed_host_is_not_reachable_by_its_key(renamed: YamlRoot) -> None:
    # One node, one name — see models/nodes.py, node_matches.
    with pytest.raises(NodeNotFound):
        renamed.find_node("edge_box_01")


def test_a_renamed_vm_resolves_by_its_name(renamed: YamlRoot) -> None:
    assert renamed.find_node("media").node.name == "media"
    with pytest.raises(NodeNotFound):
        renamed.find_node("vm1")


# ── Listings ──────────────────────────────────────────────────────────────────
#
# What these print has to be what `find_node` accepts, or the listing is telling
# you to type something the next command refuses.


def _run(app_module: object, command: str) -> str:
    app = typer.Typer()
    app.command()(getattr(app_module, command))
    result = runner.invoke(app, [])
    assert result.exit_code == 0, result.output
    return result.output


def test_host_list_shows_the_effective_name(renamed: YamlRoot) -> None:
    state.model = renamed
    output = _run(host_cli, "host_list")
    assert "edge" in output
    assert "edge_box_01" not in output


def test_vm_list_shows_the_effective_name(renamed: YamlRoot) -> None:
    state.model = renamed
    output = _run(vm_cli, "vm_list")
    assert "media" in output
    # The VM's key, and the *parent's* column, which reads the same field.
    assert "vm1" not in output
    assert "prox" in output
