"""Fixtures for the wake tests.

``valid_config_dict`` carries no MAC addresses — nothing else in labops needs
them — so this adds them here rather than in the root conftest, where every
other suite would have to ignore them.

The shape the wake tests rely on, on top of the root fixture:

* ``nas`` (bare-metal, 10.0.0.5) — has a mac. The plain packet case.
* ``ct1`` (lxc under ``prox``, vmid 101) — has a mac. A guest that *could* take a
  packet, so ``--packet`` has something to do.
* ``vm1`` (vm under ``prox``, vmid 201) — no mac. The guest that is started on its
  parent, and the one that makes ``--packet`` fail for want of a mac.
* ``edge`` (bare-metal, 10.0.0.4) — no mac. A host with nothing to send to.
"""

from typing import Any

import pytest

from models.input_conf.yaml_root import YamlRoot

NAS_MAC = "aa:bb:cc:dd:ee:01"
CT1_MAC = "aa:bb:cc:dd:ee:02"


@pytest.fixture
def wake_config_dict(valid_config_dict: dict[str, Any]) -> dict[str, Any]:
    """``valid_config_dict`` with a mac on ``nas`` and on ``ct1``."""
    valid_config_dict["hosts"]["nas"]["mac"] = NAS_MAC
    valid_config_dict["hosts"]["prox"]["lxc"]["ct1"]["mac"] = CT1_MAC
    return valid_config_dict


@pytest.fixture
def wake_config(wake_config_dict: dict[str, Any]) -> YamlRoot:
    """The validated model, which is what every wake entry point takes."""
    return YamlRoot.model_validate(wake_config_dict)
