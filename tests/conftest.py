"""Shared fixtures for the labops test suite.

All fixtures build config *dicts* in code (rather than loading the sample
YAMLs) so that path-dependent validators — ``Creds.ssh_key_path`` (FilePath)
and ``StackEntry.config_path`` (DirectoryPath) — point at real temp files and
dirs created per-test. This keeps the suite hermetic and CI-safe.
"""

from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_ssh_key(tmp_path: Path) -> Path:
    """A real file so ``Creds.ssh_key_path`` (a pydantic FilePath) validates."""
    key: Path = tmp_path / "id_test"
    key.write_text("FAKE KEY")
    return key


@pytest.fixture
def tmp_docker_dir(tmp_path: Path) -> Path:
    """A real dir so ``StackEntry.config_path`` (a pydantic DirectoryPath) validates."""
    d: Path = tmp_path / "stack"
    d.mkdir()
    return d


@pytest.fixture
def valid_config_dict(tmp_ssh_key: Path, tmp_docker_dir: Path) -> dict[str, Any]:
    """A minimal config that passes *every* YamlRoot validator.

    Shape:
      - proxmox host ``prox`` with one lxc (``ct1``) and one vm (``vm1``);
        ``vm1`` carries a docker stack ``app``.
      - bare-metal host ``edge`` with a web service.
      - host ``nas`` with ``os: unmanaged`` and a web service (an appliance
        labops doesn't update, but still proxies).

    IPs, names, proxy_names and ports are all unique; vmids are unique within
    the host. Each test gets a fresh dict it may mutate freely.
    """
    return {
        "settings": {
            "default_creds": {
                "username": "ansible",
                "ssh_key_path": str(tmp_ssh_key),
            },
        },
        "hosts": {
            "prox": {
                "type": "proxmox",
                "os": "debian",
                "ip": "10.0.0.1",
                "lxc": {
                    "ct1": {
                        "os": "alpine",
                        "ip": "10.0.0.2",
                        "vmid": 101,
                        "web_services": [{"port": 8080, "proxy_name": "ct1web"}],
                    },
                },
                "vm": {
                    "vm1": {
                        "os": "debian",
                        "ip": "10.0.0.3",
                        "vmid": 201,
                        "docker": {
                            "root_path": "/srv",
                            "stacks": {
                                "app": {
                                    "config_path": str(tmp_docker_dir),
                                    "web_services": [
                                        {"port": 9090, "proxy_name": "app"},
                                    ],
                                },
                            },
                        },
                    },
                },
            },
            "edge": {
                "type": "bare-metal",
                "os": "debian",
                "ip": "10.0.0.4",
                "web_services": [{"port": 80, "proxy_name": "edge"}],
            },
            "nas": {
                "type": "bare-metal",
                "os": "unmanaged",
                "ip": "10.0.0.5",
                "web_services": [{"port": 443, "proxy_name": "nas"}],
            },
        },
    }
