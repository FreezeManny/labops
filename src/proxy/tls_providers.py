"""Caddy-side details for each supported ACME DNS-01 provider.

The user picks a provider by name (``settings.proxy.tls.provider``, validated
against ``models.input_conf.proxy.TlsProvider``); this table says what that name
means to Caddy. Keeping it here means the render path never hardcodes a single
provider — adding one is a new ``TlsProvider`` literal plus one entry below.

labops renders the Caddyfile but does not build the Caddy image, so the DNS
plugin a provider needs must already be compiled into it (see ``plugin``).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TlsProviderSpec:
    caddy_module: str
    """Name emitted after ``dns`` inside the ``tls`` block."""

    token_env: str
    """Env var Caddy resolves the credential from at runtime. labops reads the
    same key from the .env secret store, but only to warn when it's missing."""

    plugin: str
    """caddy-dns module the Caddy image must be built with (xcaddy)."""


TLS_PROVIDERS: dict[str, TlsProviderSpec] = {
    "cloudflare": TlsProviderSpec(
        caddy_module="cloudflare",
        token_env="CF_API_TOKEN",
        plugin="github.com/caddy-dns/cloudflare",
    ),
}


def spec_for(provider: str) -> TlsProviderSpec:
    """Look up a provider's Caddy details.

    Raises on an unknown name rather than falling through to a default, so a
    provider added to ``TlsProvider`` but not here fails loudly instead of
    silently rendering someone else's directive.
    """
    try:
        return TLS_PROVIDERS[provider]
    except KeyError:
        raise ValueError(
            f"settings.proxy.tls.provider '{provider}' has no entry in TLS_PROVIDERS "
            f"(src/proxy/tls_providers.py); known providers: "
            f"{', '.join(sorted(TLS_PROVIDERS))}."
        ) from None
