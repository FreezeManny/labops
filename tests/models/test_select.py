"""Tests for the Select half of models/nodes.py — the target-selection engine.

Selection is a filter over that module's traversal, so these assert on
node *paths* (the tree address) rather than object identity. The local
``_tagged`` helper adds tags and target sets to the shared ``valid_config_dict``
rather than changing the fixture, so no existing assertion shifts.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.yaml_root import YamlRoot
from models.nodes import Selector, node_kind, select_nodes

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _tagged(cfg: dict[str, Any]) -> dict[str, Any]:
    """Add tags to the shared fixture: prox=prod, ct1=prod+edge, vm1=media."""
    hosts = cfg["hosts"]
    hosts["prox"]["tags"] = ["prod"]
    hosts["prox"]["lxc"]["ct1"]["tags"] = ["prod", "edge"]
    hosts["prox"]["vm"]["vm1"]["tags"] = ["media"]
    return cfg


def _nested(cfg: dict[str, Any]) -> dict[str, Any]:
    """Add a second level under vm1, so depth is actually exercised."""
    vm1 = cfg["hosts"]["prox"]["vm"]["vm1"]
    vm1["lxc"] = {"deep-ct": {"os": "alpine", "ip": "10.0.0.30", "vmid": 301}}
    return cfg


def _paths(cfg: dict[str, Any], sel: Selector) -> list[str]:
    model: YamlRoot = YamlRoot.model_validate(cfg)
    return ["/".join(ref.path) for ref in model.select(sel)]


# ─── Dimensions in isolation ──────────────────────────────────────────────────


def test_kind_selects_only_that_class(valid_config_dict: dict[str, Any]) -> None:
    assert _paths(valid_config_dict, Selector(kind=["lxc"])) == ["prox/ct1"]
    assert _paths(valid_config_dict, Selector(kind=["vm"])) == ["prox/vm1"]
    assert _paths(valid_config_dict, Selector(kind=["host"])) == [
        "prox",
        "edge",
        "nas",
    ]


def test_os_selects_across_kinds(valid_config_dict: dict[str, Any]) -> None:
    assert _paths(valid_config_dict, Selector(os=["debian"])) == [
        "prox",
        "prox/vm1",
        "edge",
    ]


def test_tags_match_the_node_that_carries_them(
    valid_config_dict: dict[str, Any],
) -> None:
    cfg = _tagged(valid_config_dict)
    assert _paths(cfg, Selector(tags=["prod"])) == ["prox", "prox/ct1"]
    assert _paths(cfg, Selector(tags=["media"])) == ["prox/vm1"]


def test_tags_are_not_inherited_by_children(
    valid_config_dict: dict[str, Any],
) -> None:
    # prox is tagged prod; vm1 (its child) is not, and must not be dragged in.
    cfg = _tagged(valid_config_dict)
    assert "prox/vm1" not in _paths(cfg, Selector(tags=["prod"]))


def test_under_is_inclusive_of_the_named_node(
    valid_config_dict: dict[str, Any],
) -> None:
    assert _paths(valid_config_dict, Selector(under=["prox"])) == [
        "prox",
        "prox/vm1",
        "prox/ct1",
    ]


def test_under_a_leaf_selects_exactly_that_node(
    valid_config_dict: dict[str, Any],
) -> None:
    assert _paths(valid_config_dict, Selector(under=["ct1"])) == ["prox/ct1"]


def test_under_reaches_a_nested_child(valid_config_dict: dict[str, Any]) -> None:
    cfg = _nested(valid_config_dict)
    assert _paths(cfg, Selector(under=["vm1"])) == ["prox/vm1", "prox/vm1/deep-ct"]


# ─── Combination semantics ────────────────────────────────────────────────────


def test_different_fields_are_and(valid_config_dict: dict[str, Any]) -> None:
    sel = Selector(kind=["vm"], os=["debian"])
    assert _paths(valid_config_dict, sel) == ["prox/vm1"]
    # No VM is alpine, so the conjunction is empty rather than a union.
    assert _paths(valid_config_dict, Selector(kind=["vm"], os=["alpine"])) == []


def test_values_within_a_field_are_or(valid_config_dict: dict[str, Any]) -> None:
    # Results stay in tree order (VMs before LXCs), not in the order the values
    # were given.
    cfg = _tagged(valid_config_dict)
    assert _paths(cfg, Selector(tags=["media", "edge"])) == ["prox/vm1", "prox/ct1"]
    assert _paths(cfg, Selector(kind=["vm", "lxc"])) == ["prox/vm1", "prox/ct1"]


def test_empty_selector_matches_everything_including_unmanaged(
    valid_config_dict: dict[str, Any],
) -> None:
    # Unmanaged nodes are filtered by the update runners, not by selection —
    # so `--os unmanaged` gives an honest answer rather than a silent nothing.
    paths = _paths(valid_config_dict, Selector())
    assert paths == ["prox", "prox/vm1", "prox/ct1", "edge", "nas"]
    assert Selector().is_empty is True


def test_result_order_matches_tree_order(valid_config_dict: dict[str, Any]) -> None:
    model: YamlRoot = YamlRoot.model_validate(valid_config_dict)
    everything = [ref.path for ref in model.select(Selector())]
    assert everything == [ref.path for ref in model.iter_nodes()]


# ─── Errors and coercion ──────────────────────────────────────────────────────


def test_unknown_under_name_raises_keyerror(
    valid_config_dict: dict[str, Any],
) -> None:
    model: YamlRoot = YamlRoot.model_validate(valid_config_dict)
    with pytest.raises(KeyError, match="nope"):
        model.select(Selector(under=["nope"]))


def test_scalar_shorthand_is_coerced_to_a_list() -> None:
    sel = Selector.model_validate({"kind": "lxc", "tags": "prod"})
    assert sel.kind == ["lxc"]
    assert sel.tags == ["prod"]


def test_unknown_selector_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Selector.model_validate({"knid": ["lxc"]})


def test_invalid_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Selector.model_validate({"kind": ["container"]})


def test_select_nodes_handles_a_config_without_hosts() -> None:
    assert select_nodes(None, Selector()) == []


def test_describe_renders_the_equivalent_flags() -> None:
    sel = Selector(kind=["lxc"], os=["debian"], tags=["a", "b"])
    assert sel.describe() == "--kind lxc --os debian --tag a --tag b"
    assert Selector().describe() == "(everything)"


# ─── node_kind ────────────────────────────────────────────────────────────────


def test_node_kind_distinguishes_all_three(valid_config_dict: dict[str, Any]) -> None:
    model: YamlRoot = YamlRoot.model_validate(valid_config_dict)
    kinds = {"/".join(r.path): node_kind(r.node) for r in model.iter_nodes()}
    assert kinds["prox"] == "host"
    assert kinds["prox/vm1"] == "vm"
    assert kinds["prox/ct1"] == "lxc"


# ─── Named target sets ────────────────────────────────────────────────────────


def test_named_set_resolves_like_the_equivalent_selector(
    valid_config_dict: dict[str, Any],
) -> None:
    cfg = _tagged(valid_config_dict)
    cfg["settings"]["targets"] = {"weekly": {"kind": ["vm", "lxc"]}}
    model: YamlRoot = YamlRoot.model_validate(cfg)

    from_set = model.select(model.settings.targets["weekly"])
    from_flags = model.select(Selector(kind=["vm", "lxc"]))
    assert [r.path for r in from_set] == [r.path for r in from_flags]


def test_named_set_with_unknown_under_fails_validation(
    valid_config_dict: dict[str, Any],
) -> None:
    # A typo in curated config is invisible at run time — catch it at load.
    valid_config_dict["settings"]["targets"] = {"weekly": {"under": ["ghost"]}}
    with pytest.raises(ValidationError, match="ghost"):
        YamlRoot.model_validate(valid_config_dict)


def test_named_set_error_names_the_set(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["settings"]["targets"] = {"sunday": {"under": ["ghost"]}}
    with pytest.raises(ValidationError, match="sunday"):
        YamlRoot.model_validate(valid_config_dict)


# ─── Exclude ──────────────────────────────────────────────────────────────────


def test_exclude_drops_a_named_node(valid_config_dict: dict[str, Any]) -> None:
    paths = _paths(valid_config_dict, Selector(exclude=["edge"]))
    assert "edge" not in paths
    assert "prox" in paths


def test_exclude_drops_subtree(valid_config_dict: dict[str, Any]) -> None:
    paths = _paths(valid_config_dict, Selector(exclude=["prox"]))
    assert paths == ["edge", "nas"]


def test_exclude_combines_with_positive_filters(
    valid_config_dict: dict[str, Any],
) -> None:
    sel = Selector(kind=["host"], exclude=["edge"])
    paths = _paths(valid_config_dict, sel)
    assert "edge" not in paths
    assert "prox" in paths
    assert "nas" in paths


def test_exclude_scalar_coerced_to_list() -> None:
    sel = Selector.model_validate({"exclude": "pihole"})
    assert sel.exclude == ["pihole"]


def test_exclude_unknown_name_raises(valid_config_dict: dict[str, Any]) -> None:
    model = YamlRoot.model_validate(valid_config_dict)
    with pytest.raises(KeyError, match="nope"):
        model.select(Selector(exclude=["nope"]))


def test_exclude_in_named_set_unknown_fails_validation(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["settings"]["targets"] = {"weekly": {"exclude": ["ghost"]}}
    with pytest.raises(ValidationError, match="ghost"):
        YamlRoot.model_validate(valid_config_dict)


def test_describe_includes_exclude() -> None:
    sel = Selector(kind=["lxc"], exclude=["pihole"])
    assert sel.describe() == "--kind lxc --exclude pihole"


def test_selector_with_only_exclude_is_not_empty() -> None:
    sel = Selector(exclude=["pihole"])
    assert sel.is_empty is False


def test_config_without_targets_still_validates(
    valid_config_dict: dict[str, Any],
) -> None:
    model: YamlRoot = YamlRoot.model_validate(valid_config_dict)
    assert model.settings.targets == {}


# ─── tags on the node models ──────────────────────────────────────────────────


def test_tags_default_to_empty_on_every_node_kind(
    valid_config_dict: dict[str, Any],
) -> None:
    model: YamlRoot = YamlRoot.model_validate(valid_config_dict)
    assert all(ref.node.tags == [] for ref in model.iter_nodes())


def test_tags_are_allowed_on_an_unmanaged_node(
    valid_config_dict: dict[str, Any],
) -> None:
    # tags are not a management field — an appliance can still be labelled.
    valid_config_dict["hosts"]["nas"]["tags"] = ["appliance"]
    model: YamlRoot = YamlRoot.model_validate(valid_config_dict)
    assert _paths(valid_config_dict, Selector(tags=["appliance"])) == ["nas"]
    assert model.hosts is not None
