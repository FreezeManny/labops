"""Tests for src/host/update.py — unmanaged nodes are skipped, not Ansible-run.

The same ``update`` is re-exported for VMs (src/vm/__init__.py), so the skip
behavior is covered for both. Ansible is never invoked: ``run_playbook`` is
monkeypatched to capture the inventory it would have received.
"""

import importlib
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from models.input_conf.creds import Creds
from models.input_conf.host import Host
from src.host.update import update

# ``src.host.__init__`` re-exports the ``update`` function as ``src.host.update``,
# shadowing the submodule attribute — so fetch the real module via importlib
# (which returns the sys.modules entry) to monkeypatch its ``run_playbook``.
_update_module: ModuleType = importlib.import_module("src.host.update")


def _default_creds() -> Creds:
    return Creds.model_validate({"username": "ansible", "password": "secret"})


def _managed_host(name: str = "edge", ip: str = "10.0.0.4") -> Host:
    return Host.model_validate(
        {"name": name, "type": "bare-metal", "os": "debian", "ip": ip}
    )


def _unmanaged_host(name: str = "haos", ip: str = "10.0.0.20") -> Host:
    return Host.model_validate({"name": name, "os": "unmanaged", "ip": ip})


@pytest.fixture
def captured_playbook(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace run_playbook with a stub recording its call args (rc=0 success)."""
    record: dict[str, Any] = {"called": False, "inventory": None}

    def _stub(**kwargs: object) -> SimpleNamespace:
        record["called"] = True
        record["inventory"] = kwargs.get("inventory")
        return SimpleNamespace(rc=0)

    monkeypatch.setattr(_update_module, "run_playbook", _stub)
    return record


def test_update_skips_unmanaged_and_excludes_from_inventory(
    captured_playbook: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    hosts = [_managed_host(ip="10.0.0.4"), _unmanaged_host(name="haos", ip="10.0.0.20")]
    update(hosts, _default_creds())

    assert captured_playbook["called"] is True
    # Flatten all host IPs across OS groups in the built inventory.
    children = captured_playbook["inventory"]["all"]["children"]
    all_ips = {ip for group in children.values() for ip in group["hosts"]}
    assert "10.0.0.4" in all_ips
    assert "10.0.0.20" not in all_ips

    out = capsys.readouterr().out
    assert "unmanaged" in out.lower()
    assert "haos" in out


def test_update_all_unmanaged_runs_nothing(
    captured_playbook: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
) -> None:
    hosts = [_unmanaged_host(name="haos", ip="10.0.0.20")]
    update(hosts, _default_creds())

    assert captured_playbook["called"] is False
    out = capsys.readouterr().out
    assert "No valid hosts found to update." in out


def test_update_returns_the_summary(captured_playbook: dict[str, Any]) -> None:
    # The return value is what lets `labops update` set a non-zero exit code
    # instead of only printing a failure.
    summary = update([_managed_host()], _default_creds())
    assert summary is not None
    assert summary.rc == 0


def test_update_returns_none_when_nothing_ran(
    captured_playbook: dict[str, Any],
) -> None:
    assert update([_unmanaged_host()], _default_creds()) is None
