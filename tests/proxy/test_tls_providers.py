"""Tests for src/proxy/tls_providers — the DNS-provider registry.

The point of these tests is the coupling between the user-facing provider names
(``models.input_conf.proxy.TlsProvider``) and the Caddy details keyed by them:
they must not drift, or a selectable provider would render another's directive.
"""

from typing import get_args

import pytest

from models.input_conf.proxy import TlsProvider
from src.proxy.tls_providers import TLS_PROVIDERS, spec_for


def test_registry_matches_selectable_providers() -> None:
    # Every provider a user may write has Caddy details, and vice versa. "none"
    # is the off switch, so it is deliberately absent from the registry.
    assert set(TLS_PROVIDERS) | {"none"} == set(get_args(TlsProvider))


def test_none_is_not_a_registry_entry() -> None:
    assert "none" not in TLS_PROVIDERS


def test_spec_for_returns_caddy_details() -> None:
    spec = spec_for("cloudflare")
    assert spec.caddy_module == "cloudflare"
    assert spec.token_env == "CF_API_TOKEN"
    assert spec.plugin == "github.com/caddy-dns/cloudflare"


def test_spec_for_rejects_unknown_provider() -> None:
    # A provider added to TlsProvider but not to the registry must fail loudly
    # rather than fall through to a default.
    with pytest.raises(ValueError, match="has no entry in TLS_PROVIDERS"):
        spec_for("route53")
