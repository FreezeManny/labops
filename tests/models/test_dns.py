"""Tests for models/input_conf/dns.py — the ``settings.dns`` block itself.

Deliberately thin, because ``Dns`` is deliberately thin: a suffix, and at most one
server block. Everything about *a particular server* is that server's own model
(test_pihole_block.py), the node-level ``dns`` / ``dns_name`` fields are
test_dns_fields.py, and the code that reads any of it is tests/dns/.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.dns import Dns


def _dns(**overrides: object) -> Dns:
    data: dict[str, Any] = {"suffix": ".lab"}
    data.update(overrides)
    return Dns.model_validate(data)


# ── suffix ────────────────────────────────────────────────────────────────────


def test_a_suffix_is_all_that_is_required() -> None:
    """Without a server block records are still derived, so `dns list` works."""
    dns = _dns()
    assert dns.suffix == "lab"
    assert dns.pihole is None


def test_the_suffix_is_required() -> None:
    with pytest.raises(ValidationError, match="suffix"):
        Dns.model_validate({})


@pytest.mark.parametrize(
    "configured,expected",
    [(".lab", "lab"), ("lab", "lab"), (".home.local", "home.local")],
)
def test_a_leading_dot_is_optional(configured: str, expected: str) -> None:
    """Both spellings are the same zone, so a label is always one dot from a host.

    Normalized once here rather than at every reader, which would otherwise each
    have to remember which spelling the config used.
    """
    assert _dns(suffix=configured).suffix == expected


# ── the server block ──────────────────────────────────────────────────────────


def test_a_pihole_block_is_parsed_into_its_own_model() -> None:
    dns = _dns(pihole={"target": "pihole"})
    assert dns.pihole is not None
    assert dns.pihole.target == "pihole"


def test_the_server_block_is_optional() -> None:
    """Records without a publisher is a real state, not a half-configured one."""
    assert _dns().pihole is None


def test_an_invalid_server_block_fails_the_whole_config() -> None:
    """It is validated here, not deferred to the command that would use it."""
    with pytest.raises(
        ValidationError, match="exactly one of target: or docker_stack:"
    ):
        _dns(pihole={"port": 8080})


# ── strictness ────────────────────────────────────────────────────────────────


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _dns(piholes={"target": "pihole"})


def test_the_old_flat_shape_is_rejected_rather_than_ignored() -> None:
    """`pihole_location` was one string; it is a block now, and silence would hurt.

    Rejecting rather than ignoring is what turns an upgrade into a message instead
    of a config that loads and publishes nowhere.
    """
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _dns(pihole_location="10.0.0.53")
