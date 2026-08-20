"""Tests for models/input_conf/proxy.py — Proxy, ProxyTls, ProxyDeploy, AccessList."""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.proxy import (
    AccessList,
    Proxy,
    ProxyDeploy,
    ProxyTls,
)

_TLS: dict[str, Any] = {"provider": "cloudflare"}


# ── Proxy ─────────────────────────────────────────────────────────────────────


def _proxy(**overrides: object) -> dict[str, Any]:
    data: dict[str, Any] = {
        "proxy_suffix": "home.arpa",
        "tls": _TLS,
        "default_access": "local",
        "access_lists": {"local": {"accept": ["10.0.0.0/24"]}},
    }
    data.update(overrides)
    return data


def test_proxy_valid() -> None:
    proxy = Proxy.model_validate(_proxy())
    assert proxy.proxy_suffix == "home.arpa"
    assert proxy.default_access == "local"


def test_proxy_requires_proxy_suffix() -> None:
    data = _proxy()
    del data["proxy_suffix"]
    with pytest.raises(ValidationError, match="proxy_suffix"):
        Proxy.model_validate(data)


def test_proxy_requires_access_lists() -> None:
    with pytest.raises(ValidationError, match="access_lists"):
        Proxy.model_validate({"proxy_suffix": "home.arpa"})


def test_proxy_requires_default_access() -> None:
    data = _proxy()
    del data["default_access"]
    with pytest.raises(ValidationError, match="default_access"):
        Proxy.model_validate(data)


def test_proxy_rejects_unknown_default_access() -> None:
    # The error names the bad value and the lists that would have been valid.
    with pytest.raises(
        ValidationError, match="default_access names unknown access list 'lan'"
    ) as exc:
        Proxy.model_validate(
            _proxy(
                default_access="lan",
                access_lists={
                    "local": {"accept": ["10.0.0.0/24"]},
                    "vpn": {"accept": ["100.64.0.0/10"]},
                },
            )
        )
    assert "Valid lists: local, vpn" in str(exc.value)


def test_proxy_rejects_bad_cidr() -> None:
    with pytest.raises(ValidationError):
        Proxy.model_validate(_proxy(access_lists={"local": {"accept": ["not-a-cidr"]}}))


# ── ProxyTls ──────────────────────────────────────────────────────────────


def test_proxy_tls_defaults_to_cloudflare() -> None:
    # An empty tls block selects Cloudflare with no inline token.
    tls = ProxyTls.model_validate({})
    assert tls.provider == "cloudflare"
    assert tls.token is None


def test_proxy_tls_accepts_provider_none() -> None:
    # "none" is a valid provider value — the off switch. What it *renders* is
    # covered by test_render_provider_none_serves_http / the tls_warnings tests.
    assert ProxyTls.model_validate({"provider": "none"}).provider == "none"


def test_proxy_tls_rejects_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        ProxyTls.model_validate({"provider": "letsencrypt"})


def test_proxy_tls_accepts_inline_token() -> None:
    tls = ProxyTls.model_validate({"provider": "cloudflare", "token": "cf-abc"})
    assert tls.token == "cf-abc"


def test_proxy_tls_rejects_token_env_field() -> None:
    # The env var name comes from the provider registry; there is no token_env knob.
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProxyTls.model_validate({"token_env": "MY_CF"})


def test_proxy_tls_rejects_generic_provider_fields() -> None:
    # Provider details live in the registry, not in the config: no knobs here.
    for field in ("dns_provider", "dns_options", "dns_module"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            ProxyTls.model_validate({field: "x"})


def test_proxy_tls_is_optional() -> None:
    # Omitting tls is valid -> the wildcard is served over plain HTTP.
    data = _proxy()
    del data["tls"]
    proxy = Proxy.model_validate(data)
    assert proxy.tls is None


def test_proxy_rejects_removed_deploy_fields() -> None:
    # These non-docker fields were removed in the docker-first refactor; secrets
    # and placement are now the Caddy docker stack's concern.
    for field in ("proxy_location", "caddyfile_path_remote", "env_file"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            Proxy.model_validate(_proxy(**{field: "x"}))


# ── ProxyDeploy ───────────────────────────────────────────────────────────────


def _deploy(**overrides: object) -> dict[str, Any]:
    # A docker-mode deploy: the `docker:` block's presence selects the mode.
    data: dict[str, Any] = {
        "target": "caddy-node",
        "caddyfile_dest": "/srv/caddy/Caddyfile",
        "docker": {"container": "caddy"},
    }
    data.update(overrides)
    return data


def _host_deploy(**overrides: object) -> dict[str, Any]:
    # A host-mode deploy: no `docker:` block at all.
    data: dict[str, Any] = {
        "target": "caddy-node",
        "caddyfile_dest": "/etc/caddy/Caddyfile",
    }
    data.update(overrides)
    return data


def test_proxy_deploy_docker_valid() -> None:
    d = ProxyDeploy.model_validate(_deploy())
    assert d.mode == "docker"
    assert d.docker is not None and d.docker.container == "caddy"
    # In-container config path defaults to the official image's location.
    assert d.docker.container_caddyfile_path == "/etc/caddy/Caddyfile"


def test_proxy_deploy_docker_block_selects_docker_mode() -> None:
    # Presence of the docker block => docker; absence => host.
    assert ProxyDeploy.model_validate(_deploy()).mode == "docker"
    assert ProxyDeploy.model_validate(_host_deploy()).mode == "host"


def test_proxy_deploy_docker_requires_container() -> None:
    # An empty docker block selects docker mode but names no container.
    data = _deploy(docker={})
    with pytest.raises(ValidationError, match="docker.container is required"):
        ProxyDeploy.model_validate(data)


def test_proxy_deploy_docker_container_optional_with_override() -> None:
    # A custom reload_command replaces the default `docker exec`, so no container.
    d = ProxyDeploy.model_validate(
        {
            "target": "caddy-node",
            "caddyfile_dest": "/srv/caddy/Caddyfile",
            "docker": {},
            "reload_command": "docker restart caddy",
        }
    )
    assert d.mode == "docker"
    assert d.docker is not None and d.docker.container is None
    assert d.reload_command == "docker restart caddy"


def test_proxy_deploy_reload_command_defaults_none() -> None:
    assert ProxyDeploy.model_validate(_deploy()).reload_command is None


def test_proxy_deploy_host_needs_no_docker_block() -> None:
    d = ProxyDeploy.model_validate(_host_deploy())
    assert d.mode == "host"
    assert d.docker is None


def test_proxy_deploy_rejects_relative_caddyfile_dest() -> None:
    with pytest.raises(ValidationError, match="must be an absolute path") as excinfo:
        ProxyDeploy.model_validate(_deploy(caddyfile_dest="caddy/Caddyfile"))
    # Which field is pydantic's to report now that the rule is a shared annotated
    # type (models/input_conf/paths.py) rather than a sentence naming the key.
    assert excinfo.value.errors()[0]["loc"] == ("caddyfile_dest",)


def test_proxy_deploy_rejects_unknown_docker_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ProxyDeploy.model_validate(_deploy(docker={"container": "caddy", "oops": 1}))


def test_proxy_deploy_requires_target() -> None:
    data = _deploy()
    del data["target"]
    with pytest.raises(ValidationError, match="target"):
        ProxyDeploy.model_validate(data)


def test_proxy_deploy_is_optional_on_proxy() -> None:
    assert Proxy.model_validate(_proxy()).deploy is None


def test_proxy_accepts_nested_deploy() -> None:
    proxy = Proxy.model_validate(_proxy(deploy=_host_deploy()))
    assert proxy.deploy is not None
    assert proxy.deploy.mode == "host"
    assert proxy.deploy.target == "caddy-node"


# ── AccessList ──────────────────────────────────────────────────────────────


def test_access_list_accept_only() -> None:
    al = AccessList.model_validate({"accept": ["10.0.0.0/24"]})
    assert al.deny is None


def test_access_list_accept_with_deny_carveout() -> None:
    al = AccessList.model_validate(
        {"accept": ["10.0.0.0/24"], "deny": ["10.0.0.66/32"]}
    )
    assert al.accept is not None and al.deny is not None


def test_access_list_requires_accept() -> None:
    # deny-only (no accept) is rejected — accept is mandatory.
    with pytest.raises(ValidationError, match="accept"):
        AccessList.model_validate({"deny": ["10.0.0.66/32"]})


def test_access_list_rejects_empty_accept() -> None:
    with pytest.raises(ValidationError, match="at least one 'accept' CIDR"):
        AccessList.model_validate({"accept": []})
