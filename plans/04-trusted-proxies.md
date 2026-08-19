# Ticket 4 — `trusted_proxies` / `client_ip`

**Breaking:** no (purely additive). **Depends on:** nothing.
**The only change in this refactor that fixes a fail-open condition.**

## Why

Access-list matchers render as Caddy's `remote_ip`, which is the **connecting socket's**
address. Put a CDN or upstream proxy in front of Caddy and every request arrives from that
proxy's address:

1. First symptom: every route 403s, because no client is in your LAN accept list.
2. The obvious "fix" is to add the CDN's ranges to an accept list — at which point
   **every client on the internet is inside your accept list**, because they all arrive via
   the CDN.

The config still looks correct throughout. This is plausible here specifically: the TLS
block is already Cloudflare-shaped (`src/proxy/tls_providers.py` has exactly one provider,
`cloudflare`), and proxying through Cloudflare rather than DNS-only is the common setup.

Caddy's `client_ip` matcher reads a trusted `X-Forwarded-For` instead, but only when the
server is told which proxies to trust.

## Target config

```yaml
settings:
  proxy:
    trusted_proxies: [173.245.48.0/20, 103.21.244.0/22]   # new, optional
```

Unset (the default) changes nothing about today's behaviour.

## Scope

### 1. Model

`models/input_conf/proxy.py` — add to `Proxy`:

```python
trusted_proxies: Optional[List[IPvAnyNetwork]]
```

Rejected if present but empty. `IPvAnyNetwork` is already imported and used by `AccessList`.
The field description must carry the security warning (see Risks).

### 2. Render context

`_render_context` (`src/proxy/render.py:140-192`) gains **two** variables. Its docstring is
the documented contract for `settings.proxy.template` ("treat additions as additive and
removals as breaking"), so document both there:

- `trusted_proxies` — CIDR strings, or `None`
- `ip_matcher` — `"client_ip"` when `trusted_proxies` is set, else `"remote_ip"`

Pass `ip_matcher` explicitly rather than deriving it in the template, so a custom template
that overrides only the `routes` block still gets the right matcher.

`render.py:219` uses `StrictUndefined`, so both keys must always be present in the context —
`None` included, never omitted.

### 3. Template

`ansible/files/proxy/Caddyfile.j2`:

- Fill the currently-empty `{% block global_options %}{% endblock %}` when `trusted_proxies`
  is set. Caddy global options are a brace block *before* the site block, which is exactly
  where that block sits:

  ```
  {
  	servers {
  		trusted_proxies static 173.245.48.0/20 103.21.244.0/22
  	}
  }
  ```

- In the `routes` block, swap `remote_ip` → `{{ ip_matcher }}` in **both** matcher lines
  (the `_deny` matcher and the `_notallowed` matcher).

No other template change: both matchers are already `{% if %}`-guarded.

## Tests

Extend `tests/proxy/test_render.py`:

- unset → no global-options stanza, matchers still say `remote_ip`
- set → the `servers { trusted_proxies static … }` stanza appears, matchers say `client_ip`
- empty list → validation error

And in `tests/proxy/test_custom_template.py`: a custom template still renders under
`StrictUndefined` now that two keys were added to the context.

## Docs

- `docs/guides/proxy.md` — a section on the CDN failure mode above, and an explicit warning
  to list only the proxy directly in front of Caddy.
- `ansible/files/proxy/README.md` — this file is hand-written, tracked, and included into
  the docs site via `docs/guides/proxy-templates.md:10-13`. Add `trusted_proxies` and
  `ip_matcher` to its **variables in scope** table, and extend the "overriding `routes`
  takes on the access lists" caveat (`:194-197`) to note it now also takes on the matcher
  choice.

## Verification

```bash
just check && just test
labops proxy render                          # no trusted_proxies: expect remote_ip, no `{ servers ... }`
# add trusted_proxies to the config, then:
labops proxy render                          # expect client_ip and the global-options stanza
labops proxy access                          # resolved CIDRs must be unchanged either way
```

## Risks

**This field is itself security-relevant.** Switching to `client_ip` means trusting an
`X-Forwarded-For` header. Listing a range that is *not* a proxy under your control lets any
client in that range forge its apparent address and walk straight through every access list.

The docs must state: list only the proxy in front of Caddy, never `0.0.0.0/0`. Consider
rejecting an all-addresses value outright — decide during implementation.

## Do not

- Do not switch to `client_ip` unconditionally. Without `trusted_proxies` configured, Caddy
  would trust a forgeable header from anyone.
- Do not derive `ip_matcher` inside the template only. A custom template overriding `routes`
  would then have to re-derive it and could silently keep `remote_ip`.
