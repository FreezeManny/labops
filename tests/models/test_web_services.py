"""Tests for web-service port collision (shared validator) and WebServices indexing."""

import pytest
from pydantic import ValidationError

from models.input_conf.lxc import LXC
from models.input_conf.unmanaged import Unmanaged
from models.input_conf.web_services import WebServices


def test_webservices_indexing() -> None:
    ws = WebServices.model_validate(
        [{"port": 80, "proxy_name": "a"}, {"port": 81, "proxy_name": "b"}]
    )
    assert ws[0].port == 80
    assert ws[1].proxy_name == "b"


def test_duplicate_port_within_web_services_rejected() -> None:
    # check_duplicate_ws_ports is shared; exercise it via Unmanaged.
    with pytest.raises(ValidationError, match="Duplicate port found: 80"):
        Unmanaged.model_validate(
            {
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
    node = Unmanaged.model_validate(
        {"ip": "10.0.0.5", "web_services": [{"port": 80}, {"port": 443}]}
    )
    assert node.web_services is not None
    assert [w.port for w in node.web_services.root] == [80, 443]
