"""Tests for web-service port collision (shared validator), proxy_name shape and
WebServices indexing."""

import pytest
from pydantic import ValidationError

from models.input_conf.host import Host
from models.input_conf.lxc import LXC
from models.input_conf.web_services import WebServices


def test_webservices_indexing() -> None:
    ws = WebServices.model_validate(
        [{"port": 80, "proxy_name": "a"}, {"port": 81, "proxy_name": "b"}]
    )
    assert ws[0].port == 80
    assert ws[1].proxy_name == "b"


def test_duplicate_port_within_web_services_rejected() -> None:
    # check_duplicate_ws_ports is shared; exercise it via Host.
    with pytest.raises(ValidationError, match="Duplicate port found: 80"):
        Host.model_validate(
            {
                "os": "debian",
                "ip": "10.0.0.5",
                "web_services": [{"port": 80}, {"port": 80}],
            }
        )


def test_duplicate_port_across_web_services_and_docker_stack_rejected(
    tmp_docker_dir: object,
) -> None:
    # Same port used by an LXC's web_service and one of its docker stacks.
    with pytest.raises(ValidationError, match="Duplicate port found: 9090"):
        LXC.model_validate(
            {
                "ip": "10.0.0.2",
                "os": "alpine",
                "vmid": 101,
                "web_services": [{"port": 9090, "proxy_name": "x"}],
                "docker": {
                    "root_path": "/srv",
                    "stacks": {
                        "app": {
                            "config_path": str(tmp_docker_dir),
                            "web_services": [{"port": 9090, "proxy_name": "y"}],
                        },
                    },
                },
            }
        )


def test_unique_ports_accepted() -> None:
    node = Host.model_validate(
        {
            "os": "debian",
            "ip": "10.0.0.5",
            "web_services": [{"port": 80}, {"port": 443}],
        }
    )
    assert node.web_services is not None
    assert [w.port for w in node.web_services.root] == [80, 443]


# ─── proxy_name shape ─────────────────────────────────────────────────────────
#
# A proxy_name becomes a DNS label *and* a Caddy matcher name, so anything the
# Caddyfile grammar cannot hold has to be rejected at validate time — otherwise
# it only fails on the target, mid-deploy.


@pytest.mark.parametrize(
    "name",
    ["home", "dfs-aip", "z2mqtt", "a", "Home", "pi-hole-2", "x" * 63],
)
def test_valid_proxy_names_accepted(name: str) -> None:
    ws = WebServices.model_validate([{"port": 80, "proxy_name": name}])
    assert ws[0].proxy_name == name


@pytest.mark.parametrize(
    "name",
    [
        "has space",
        "has.dot",  # would silently add a subdomain level
        "-leading",
        "trailing-",
        "under_score",
        "curly{brace}",
        "with/slash",
        "",
    ],
)
def test_invalid_proxy_names_rejected(name: str) -> None:
    with pytest.raises(ValidationError, match="not a valid hostname label"):
        WebServices.model_validate([{"port": 80, "proxy_name": name}])


def test_overlong_proxy_name_rejected() -> None:
    with pytest.raises(ValidationError, match="longer than 63 characters"):
        WebServices.model_validate([{"port": 80, "proxy_name": "x" * 64}])


def test_absent_proxy_name_still_allowed() -> None:
    # No proxy_name means "not routed" — still a legal web_service.
    ws = WebServices.model_validate([{"port": 80}])
    assert ws[0].proxy_name is None
