"""Tests for src/proxy — route discovery and Caddyfile rendering."""

from typing import Any

from models.input_conf.yaml_root import YamlRoot
from src.proxy import find_routes, render_caddyfile


def _model(cfg: dict[str, Any]) -> YamlRoot:
    return YamlRoot.model_validate(cfg)


# ── find_routes ─────────────────────────────────────────────────────────────


def test_find_routes_collects_all_web_services(
    valid_config_dict: dict[str, Any],
) -> None:
    routes = find_routes(_model(valid_config_dict))
    by_name = {r.proxy_name: r for r in routes}
    # node-level (lxc, host) + docker-stack-level services are all collected.
    assert set(by_name) == {"ct1web", "app", "edge", "nas"}
    # a docker stack's service is reached at its host node's IP (vm1 = 10.0.0.3).
    assert str(by_name["app"].target_ip) == "10.0.0.3"
    assert by_name["app"].port == 9090


def test_find_routes_skips_entries_without_proxy_name(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["hosts"]["edge"]["web_services"].append({"port": 9999})
    names = {r.proxy_name for r in find_routes(_model(valid_config_dict))}
    assert "edge" in names  # the named one survives; the unnamed one is skipped


# ── render_caddyfile ────────────────────────────────────────────────────────


def test_render_contains_wildcard_and_tls(valid_config_dict: dict[str, Any]) -> None:
    out = render_caddyfile(_model(valid_config_dict))
    assert "*.example.test {" in out
    assert (
        "dns spaceship {env.LIBDNS_SPACESHIP_APIKEY} {env.LIBDNS_SPACESHIP_APISECRET}"
        in out
    )


def test_render_default_access_is_local_remote_ip(
    valid_config_dict: dict[str, Any],
) -> None:
    out = render_caddyfile(_model(valid_config_dict))
    # edge has no explicit access -> default (local) list, matched via remote_ip.
    assert "@edge host edge.example.test" in out
    assert "@edge_notallowed not remote_ip 10.0.0.0/24" in out
    assert "reverse_proxy 10.0.0.4:80" in out


def test_render_accept_all_list_is_open(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["settings"]["proxy"]["access_lists"]["open"] = {
        "accept": ["0.0.0.0/0"]
    }
    valid_config_dict["hosts"]["nas"]["web_services"][0]["access"] = ["open"]
    out = render_caddyfile(_model(valid_config_dict))
    assert "@nas host nas.example.test" in out
    assert "reverse_proxy 10.0.0.5:443" in out
    # accept 0.0.0.0/0 renders a matcher that never blocks anything.
    assert "@nas_notallowed not remote_ip 0.0.0.0/0" in out
    assert "@nas_deny" not in out


def test_render_deny_wins_and_precedes_accept(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["settings"]["proxy"]["access_lists"]["local"] = {
        "default": True,
        "accept": ["10.0.0.0/24"],
        "deny": ["10.0.0.66/32"],
    }
    out = render_caddyfile(_model(valid_config_dict))
    deny_idx = out.index("@edge_deny remote_ip 10.0.0.66/32")
    accept_idx = out.index("@edge_notallowed not remote_ip 10.0.0.0/24")
    assert deny_idx < accept_idx  # deny is evaluated first


def test_render_union_of_named_lists(valid_config_dict: dict[str, Any]) -> None:
    valid_config_dict["settings"]["proxy"]["access_lists"]["vpn"] = {
        "accept": ["100.64.0.0/10"]
    }
    valid_config_dict["hosts"]["edge"]["web_services"][0]["access"] = ["local", "vpn"]
    out = render_caddyfile(_model(valid_config_dict))
    assert "@edge_notallowed not remote_ip 10.0.0.0/24 100.64.0.0/10" in out
