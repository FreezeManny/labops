"""Tests for src/proxy — route discovery and Caddyfile rendering."""

from typing import Any

import pytest

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


def test_find_routes_accepts_the_short_form(
    valid_config_dict: dict[str, Any],
) -> None:
    # `web_services: {name: port}` has to reach the Caddyfile like the list form.
    valid_config_dict["hosts"]["prox"]["lxc"]["ct1"]["web_services"] = {"ct1web": 8080}
    route = next(
        r for r in find_routes(_model(valid_config_dict)) if r.proxy_name == "ct1web"
    )
    assert str(route.target_ip) == "10.0.0.2"
    assert route.port == 8080


# ── render_caddyfile ────────────────────────────────────────────────────────


def test_render_contains_wildcard_and_tls(valid_config_dict: dict[str, Any]) -> None:
    out = render_caddyfile(_model(valid_config_dict))
    assert "*.example.test {" in out
    assert "dns cloudflare {env.CF_API_TOKEN}" in out


def test_render_records_required_plugin(valid_config_dict: dict[str, Any]) -> None:
    # labops can't verify the image, so the provider's plugin is documented in
    # the generated file's header.
    out = render_caddyfile(_model(valid_config_dict))
    assert "github.com/caddy-dns/cloudflare" in out


def test_render_without_tls_omits_plugin_note(
    valid_config_dict: dict[str, Any],
) -> None:
    del valid_config_dict["settings"]["proxy"]["tls"]
    out = render_caddyfile(_model(valid_config_dict))
    assert "caddy-dns" not in out


def test_render_includes_access_log(valid_config_dict: dict[str, Any]) -> None:
    # The site emits an access log to stdout so denied (403) requests are visible.
    out = render_caddyfile(_model(valid_config_dict))
    assert "log {" in out
    assert "output stdout" in out


def test_render_inline_token_is_literal(valid_config_dict: dict[str, Any]) -> None:
    # An inline token is rendered verbatim (no {env.*} placeholder).
    valid_config_dict["settings"]["proxy"]["tls"] = {
        "provider": "cloudflare",
        "token": "cf-secret-abc",
    }
    out = render_caddyfile(_model(valid_config_dict))
    assert "dns cloudflare cf-secret-abc" in out
    assert "dns cloudflare {env" not in out  # no placeholder when inlined


def test_render_without_tls_serves_http(valid_config_dict: dict[str, Any]) -> None:
    # No tls -> plain-HTTP wildcard site, no tls block, no cert provisioning.
    del valid_config_dict["settings"]["proxy"]["tls"]
    out = render_caddyfile(_model(valid_config_dict))
    assert "http://*.example.test {" in out
    assert "*.example.test {" not in out.replace("http://*.example.test {", "")
    assert "tls {" not in out
    assert "dns " not in out
    # routing still renders as usual
    assert "@edge host edge.example.test" in out
    assert "reverse_proxy 10.0.0.4:80" in out


def test_render_provider_none_serves_http(valid_config_dict: dict[str, Any]) -> None:
    # provider: none disables TLS even with a tls block present.
    valid_config_dict["settings"]["proxy"]["tls"] = {"provider": "none"}
    out = render_caddyfile(_model(valid_config_dict))
    assert "http://*.example.test {" in out
    assert "tls {" not in out


def test_render_https_upstream_skips_verify(valid_config_dict: dict[str, Any]) -> None:
    # edge (10.0.0.4:80) marked https -> https:// upstream + insecure transport.
    valid_config_dict["hosts"]["edge"]["web_services"][0]["https"] = True
    out = render_caddyfile(_model(valid_config_dict))
    assert "reverse_proxy https://10.0.0.4:80 {" in out
    assert "transport http {" in out
    assert "tls_insecure_skip_verify" in out


def test_render_http_upstream_has_no_transport(
    valid_config_dict: dict[str, Any],
) -> None:
    # nas defaults to plain http -> bare reverse_proxy, no transport block.
    out = render_caddyfile(_model(valid_config_dict))
    assert "reverse_proxy 10.0.0.5:443\n" in out
    assert "https://10.0.0.5" not in out


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


# ── trusted_proxies / ip_matcher ────────────────────────────────────────────


def test_render_without_trusted_proxies_uses_remote_ip(
    valid_config_dict: dict[str, Any],
) -> None:
    out = render_caddyfile(_model(valid_config_dict))
    assert "remote_ip" in out
    assert "client_ip" not in out
    assert "trusted_proxies static" not in out


def test_render_with_trusted_proxies_uses_client_ip(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["settings"]["proxy"]["trusted_proxies"] = [
        "173.245.48.0/20",
        "103.21.244.0/22",
    ]
    out = render_caddyfile(_model(valid_config_dict))
    assert "client_ip" in out
    assert "not client_ip" in out
    # Matchers must not use remote_ip when trusted_proxies is set.
    assert "not remote_ip" not in out
    assert "trusted_proxies static 173.245.48.0/20 103.21.244.0/22" in out


def test_render_trusted_proxies_global_options_precede_site(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["settings"]["proxy"]["trusted_proxies"] = ["10.0.0.1/32"]
    out = render_caddyfile(_model(valid_config_dict))
    assert out.index("trusted_proxies static") < out.index("*.example.test {")


def test_render_trusted_proxies_empty_list_rejected(
    valid_config_dict: dict[str, Any],
) -> None:
    valid_config_dict["settings"]["proxy"]["trusted_proxies"] = []
    with pytest.raises(Exception, match="must not be empty"):
        _model(valid_config_dict)
