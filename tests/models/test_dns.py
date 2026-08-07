"""Tests for models/input_conf/dns.py — the settings.dns block.

Node-level DNS fields (``dns``, ``dns_name``) and the YamlRoot validators that
depend on this block live in test_dns_fields.py; the src-level plumbing that reads
it is in tests/dns/.
"""

import pytest
from pydantic import ValidationError

from models.input_conf.dns import (
    DEFAULT_UPGRADE_COMMAND,
    PIHOLE_PASSWORD_ENV,
    Dns,
)


def _dns(**overrides: object) -> Dns:
    data: dict[str, object] = {
        "local_dns_suffix": ".lab",
        "pihole_location": "10.0.0.53",
    }
    data.update(overrides)
    return Dns.model_validate(data)


# ── Required fields ───────────────────────────────────────────────────────────


def test_dns_valid() -> None:
    dns = Dns.model_validate(
        {"local_dns_suffix": "home.local", "pihole_location": "10.0.0.53"}
    )
    assert dns.local_dns_suffix == "home.local"
    assert str(dns.pihole_location) == "10.0.0.53"


def test_dns_requires_local_dns_suffix() -> None:
    with pytest.raises(ValidationError, match="local_dns_suffix"):
        Dns.model_validate({"pihole_location": "10.0.0.53"})


def test_pihole_location_is_optional() -> None:
    # Records are still derived without it; only the commands that talk to a
    # Pi-hole need to know where one is, and they say so when it is missing.
    dns = Dns.model_validate({"local_dns_suffix": "home.local"})
    assert dns.pihole_location is None
    assert dns.suffix == "home.local"


def test_pihole_location_accepts_a_node_name() -> None:
    # One field serves both jobs: an address for the API, and the node behind it
    # for `dns upgrade`. A name is resolved through the config at use time.
    assert _dns(pihole_location="pihole").pihole_location == "pihole"


def test_pihole_location_accepts_an_ip() -> None:
    assert _dns(pihole_location="10.0.0.53").pihole_location == "10.0.0.53"


@pytest.mark.parametrize("value", ["", "   "])
def test_blank_pihole_location_rejected(value: str) -> None:
    # Absent means "not configured yet"; blank is a mistake.
    with pytest.raises(ValidationError, match="must not be empty"):
        _dns(pihole_location=value)


def test_a_list_of_addresses_is_rejected() -> None:
    # Only one instance is supported: the secret store holds a single
    # PIHOLE_PASSWORD, so a list would assume they share one API password. A second
    # Pi-hole is fed by replication (nebula-sync), not by labops.
    with pytest.raises(ValidationError):
        _dns(pihole_location=["10.0.0.53", "10.0.0.54"])


def test_dns_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _dns(pihole_locations="10.0.0.53")


# ── API access ────────────────────────────────────────────────────────────────


def test_api_defaults_match_pihole_defaults() -> None:
    dns = _dns()
    assert dns.api_port == 80
    assert dns.api_scheme == "http"
    assert dns.password is None


def test_api_port_and_scheme_are_configurable() -> None:
    dns = _dns(api_port=8080, api_scheme="https")
    assert dns.api_port == 8080
    assert dns.api_scheme == "https"


def test_unknown_api_scheme_rejected() -> None:
    with pytest.raises(ValidationError):
        _dns(api_scheme="ftp")


def test_password_env_var_name() -> None:
    # src/dns/sync.py reads this key from the .env store; pinned so a rename has
    # to be deliberate rather than silently breaking everyone's secret store.
    assert PIHOLE_PASSWORD_ENV == "PIHOLE_PASSWORD"


# ── upgrade_command ───────────────────────────────────────────────────────────


def test_upgrade_command_defaults_to_the_pihole_updater() -> None:
    assert _dns().upgrade_command == DEFAULT_UPGRADE_COMMAND == "pihole -up"


def test_upgrade_command_can_be_replaced() -> None:
    # e.g. `pihole -up --check-only` to report without upgrading.
    assert (
        _dns(upgrade_command="pihole -up --check-only").upgrade_command
        == "pihole -up --check-only"
    )


@pytest.mark.parametrize("command", ["", "   "])
def test_empty_upgrade_command_rejected(command: str) -> None:
    # An empty command would run a blank shell command on the target.
    with pytest.raises(ValidationError, match="must not be empty"):
        _dns(upgrade_command=command)


# ── suffix normalization ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "configured,expected",
    [(".lab", "lab"), ("lab", "lab"), (".home.local", "home.local")],
)
def test_suffix_strips_a_leading_dot(configured: str, expected: str) -> None:
    # Both spellings mean the same zone, so a hostname is always exactly one dot
    # away from its label.
    assert _dns(local_dns_suffix=configured).suffix == expected


def test_local_dns_suffix_is_preserved_verbatim() -> None:
    # `suffix` normalizes; the configured value itself is left alone.
    assert _dns(local_dns_suffix=".lab").local_dns_suffix == ".lab"
