"""Tests for models/input_conf/pihole.py — the ``settings.dns.pihole`` block.

Two things this block decides on its own, before anything resolves it: which of
the two location keys was given, and how to reach the API. Both are checked here
against the raw block; what a location resolves *to* is tests/dns/.
"""

from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.pihole import PIHOLE_PASSWORD_ENV, Pihole


def _pihole(**overrides: object) -> Pihole:
    data: dict[str, Any] = {"target": "pihole"}
    data.update(overrides)
    return Pihole.model_validate(data)


# ── exactly one location ──────────────────────────────────────────────────────


def test_a_target_names_the_machine_it_is_installed_on() -> None:
    block = _pihole()
    assert block.target == "pihole"
    assert block.docker_stack is None


def test_a_docker_stack_names_the_container_running_it() -> None:
    block = Pihole.model_validate({"docker_stack": "pihole"})
    assert block.docker_stack == "pihole"
    assert block.target is None


def test_neither_key_is_rejected() -> None:
    with pytest.raises(
        ValidationError, match="exactly one of target: or docker_stack:"
    ):
        Pihole.model_validate({"port": 8080})


def test_both_keys_are_rejected() -> None:
    """The two would disagree about whether `dns upgrade` can run."""
    with pytest.raises(ValidationError, match="sets both target: and docker_stack:"):
        Pihole.model_validate({"target": "pihole", "docker_stack": "pihole"})


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_location_is_the_missing_location_it_is(blank: str) -> None:
    with pytest.raises(
        ValidationError, match="exactly one of target: or docker_stack:"
    ):
        Pihole.model_validate({"target": blank})


def test_a_blank_key_does_not_shadow_the_one_that_was_set() -> None:
    """Normalized to None, not merely ignored.

    Everything downstream dispatches on which key is None, so a blank left in
    place would still be picked up as the location and resolved to nothing.
    """
    block = Pihole.model_validate({"target": "  ", "docker_stack": "pihole"})
    assert block.target is None
    assert block.docker_stack == "pihole"


def test_a_location_is_stripped() -> None:
    assert _pihole(target="  pihole  ").target == "pihole"


# ── scheme and port ───────────────────────────────────────────────────────────


def test_https_is_the_default_because_the_password_is_sent_in_the_body() -> None:
    block = _pihole()
    assert block.scheme == "https"
    assert block.port == 443


def test_choosing_http_moves_the_port_with_it() -> None:
    block = _pihole(scheme="http")
    assert block.port == 80


def test_an_explicit_port_wins_over_the_scheme() -> None:
    assert _pihole(scheme="https", port=8080).port == 8080


def test_an_explicit_port_wins_even_when_it_matches_the_other_scheme() -> None:
    """`port: 80` on https is unusual, but it was stated rather than defaulted."""
    assert _pihole(scheme="https", port=80).port == 80


def test_an_unknown_scheme_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _pihole(scheme="ftp")


# ── the rest of the block ─────────────────────────────────────────────────────


def test_a_password_may_be_inline_though_the_env_store_is_preferred() -> None:
    assert _pihole(password="hunter2").password == "hunter2"
    assert PIHOLE_PASSWORD_ENV == "PIHOLE_PASSWORD"


def test_no_password_is_legal_here() -> None:
    """Where it comes from is resolved at run time, not declared in the block."""
    assert _pihole().password is None


def test_unknown_keys_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _pihole(upgrade_command="pihole -up")
