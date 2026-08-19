# Config schema refactor — plan index

Eight independent tickets reworking `homelab.yml`, labops' entire input surface. Each ticket
file is self-contained: open exactly one in a fresh session and it carries the context it
needs.

| # | Ticket | Breaking | File |
| --- | --- | --- | --- |
| 1 | Delete `test-samples/` | no | [01-delete-test-samples.md](01-delete-test-samples.md) |
| 2 | Path resolution without `chdir` | no | [02-path-resolution.md](02-path-resolution.md) |
| 3 | `labops proxy access` | no | [03-proxy-access-command.md](03-proxy-access-command.md) |
| 4 | `trusted_proxies` / `client_ip` | no | [04-trusted-proxies.md](04-trusted-proxies.md) |
| 5 | `Selector.exclude` | no | [05-selector-exclude.md](05-selector-exclude.md) |
| 6 | `default_access` + reject deny-carrying unions | **yes** | [06-default-access.md](06-default-access.md) |
| 7 | `settings.dns` restructure | **yes** | [07-dns-block.md](07-dns-block.md) |
| 8 | `creds.password`, consistency fixes, secret refs | **yes** | [08-creds-and-secret-refs.md](08-creds-and-secret-refs.md) |

Tickets 1–5 are entirely non-breaking and could ship on their own; 6–8 change the config
format. Release sequencing and version numbering are out of scope for these plans.

## Why this refactor

A review of `models/input_conf/` turned up modelling problems that are cheap to fix now and
expensive later:

- **Access lists** carry a `default: true` flag on each entry, so "exactly one list is the
  default" needs a validator to enforce a constraint that a single field would make
  unrepresentable-if-wrong. Worse, they can fail *open*: matchers render as Caddy's
  `remote_ip`, so behind a CDN every client presents the proxy's address and the lists
  silently stop discriminating. A service's `access` also unions the `deny` sets of every
  list it names, so a LAN-scoped exclusion leaks onto clients arriving via an unrelated
  list. And there is no way to see what a route resolves to without reading rendered
  matchers by eye.
- **`settings.dns`** mixes one vendor-neutral key (`local_dns_suffix`) with four
  Pi-hole-specific ones, and `pihole_location` is a single string overloaded four ways
  (node name / IP / vmid / docker stack name) that labops resolves by *guessing*.
- **Secrets** each have a separate hardcoded env var name (`PIHOLE_PASSWORD`,
  `CF_API_TOKEN`) with no way to choose a different one, plus an inline clear-text escape
  hatch per field.
- **Path fields** validate only because `src/utils/yaml_validator.py` calls `os.chdir()`
  before `model_validate`, making relative-path semantics a function of process-global state.
- Assorted inconsistencies: `default_creds` required even for a render-only config,
  `creds.passwd` vs `dns.password`, `root_path` unvalidated while `caddyfile_dest` is,
  `Host.name` documented as unsettable but behaving as an override, `Selector` with no way to
  exclude anything.

Goal: every constraint expressed by the shape of the schema rather than by a validator, and
nothing resolved by guessing.

## Decisions already settled

Do not relitigate these. Several were considered at length and deliberately rejected.

| Question | Decision |
| --- | --- |
| Back-compat | **Clean break.** No deprecation aliases, no migration errors, no `version:` key. Old spellings fail with pydantic's "Extra inputs are not permitted". |
| `access_lists` | Stays **required**. `default_access` is also required and must name one of its keys. |
| `access: none` / `default_access: none` | **Dropped.** "none" reads as "no access" but would have meant "no restriction". A service resolves to the default list or to named lists — nothing else. |
| `accept: any` | **Declined.** `accept` stays required and non-empty; `[0.0.0.0/0, ::/0]` remains how "public" is written. |
| IPv6 open-list trap | **Docs only**, no code. `docs/guides/proxy.md:100-102` is therefore load-bearing prose — ticket 1 deletes the sample that carried the same warning in a comment. |
| Access-list extras | **In:** `trusted_proxies`/`client_ip` (4), rejecting deny-carrying unions (6), `proxy access` (3). **Out:** 403→404 responses, dead-deny and unused-list checks, node-level `access` inheritance. |
| `${VAR}` semantics | A *reference*, not substitution: it names which env var holds the secret. Built-in names stay as defaults; `${VAR}` overrides the name. Secret fields only — never `reload_command` / `upgrade_command`, which are remote shell strings. |
| `tls.token: ${VAR}` | Renders as Caddy's `{env.VAR}` — the secret never enters the Caddyfile. |
| `creds.password: ${VAR}` | Resolved **at use time** in `src/utils/inventory.py`. No implicit default env var name. |
| Path handling | Drop `os.chdir`, **keep** existence checks, resolve via pydantic validation context with a `Path.cwd()` fallback. |
| `test-samples/` | **Delete**, rather than adding the test coverage it never had. |
| `os: unmanaged` | **Keep as-is.** Splitting it into `os` + `managed: false` was proposed and rejected — the only case it would unlock is an unmanaged Proxmox parent with managed guests. |
| `type: bare-metal \| proxmox` | **Keep the field, rename it to `hypervisor` (`none \| proxmox`, default `none`) — ticket 8, A6.** Inferring it from the presence of `lxc:`/`vm:` was proposed and rejected: you would lose the ability to declare a Proxmox node before it has guests, and with two hypervisors there is nothing to infer *which* one from. Renaming fixes two warts: `type: bare-metal` is a false statement on a VM, and `type` collides with the selector's `kind` (see the comment at `models/select.py:29-31`, written to defuse exactly that). The missing `VM` gate — `Host` has `check_proxmox_support`, `VM` does not, so `type: bare-metal` plus a nested `lxc:` block validates on a VM and errors on a Host — is **ticket 8, A5**, phrased as `== "proxmox"` so a future third value cannot inherit LXC support. |

## Sequencing

Only four things constrain the order; everything else is independent.

- **Ticket 1 first** — both sample YAMLs contain nearly every key that 6, 7 and 8 rename.
  Delete them up front and no later ticket has to edit them.
- **Ticket 2 before ticket 8** — the `env_file` existence check needs the validation context
  ticket 2 introduces (and lives in ticket 2 as a result).
- **Ticket 3 before tickets 4 and 6** — `proxy access` is the tool that verifies neither of
  them changed a resolved CIDR set.
- **Ticket 7 before phase B of ticket 8** — `Dns.password` becomes `Pihole.password`; target
  the secret-ref work at its final address.
- Within ticket 8, phase A (`passwd` → `password`) precedes phase B (the `SecretRef` type):
  both rewrite the same field.

## Conventions across all tickets

- **Docs are never a separate ticket.** Each change invalidates specific prose, so each
  ticket carries its own. Otherwise `main` sits in a state where the guides describe a schema
  that does not exist.
- **`docs/configuration/*.md`, `docs/commands/*.md` and `docs/labops.schema.json` are
  generated and git-ignored** (`docs/gen_docs.py`, run by `just docs-gen`). Model docstrings
  and `Field(description=…)` *are* those docs — edit the models, not the output. Hand-written
  docs are `docs/index.md`, `getting-started.md`, `editor-setup.md`, `development.md`,
  `docs/guides/*.md`, and `ansible/files/proxy/README.md` (which is included into the site).
- **Tests build config dicts in Python**, never YAML — see `tests/conftest.py:1-7`. Nothing
  loads a `.yml` file, and `validate_yaml` has zero coverage today (ticket 2 adds the first).
- `tests/conftest.py` holds two fixtures every suite depends on: `valid_config_dict` (:31) and
  `dns_config_dict` (:107). Fix those first in tickets 6 and 7 respectively; it unblocks
  everything downstream.

## Per-ticket verification

```bash
just check          # ruff + ty
just test           # pytest
just docs-gen       # must not KeyError — ticket 7 adds a model to gen_docs.py's PAGES table
just docs-build     # mkdocs --strict
```

## Known risks

- **`trusted_proxies` (ticket 4) is itself security-relevant.** `client_ip` trusts an
  `X-Forwarded-For` header; listing a range that is not a proxy under your control lets
  clients in that range forge their apparent address and bypass every access list. Docs must
  say: only the proxy directly in front of Caddy, never `0.0.0.0/0`.
- **`docs.yml` only fires on `release: published`**, and `gen_docs.py` hard-fails with a
  `KeyError` when a model named in its `PAGES` table disappears. So a schema-affecting rename
  can reach PyPI before the docs build is ever attempted. Run `just docs-build` locally before
  merging tickets 6 and 7. (Adding it to `test.yml` was offered and not taken.)
- **Three conflict hotspots** if tickets land as separate branches:
  `models/input_conf/yaml_root.py` (tickets 5, 6, 7, 8), `tests/conftest.py` (6, 7), and
  `models/input_conf/proxy.py` (4, 6, and phase B of 8).

## Deferred — reviewed, not scheduled

Raised during the review and consciously left out. Listed so they are not rediscovered as
novel:

- **`Host`/`VM`/`LXC` field triplication.** Nine fields and three validators written three
  times across `host.py`, `lxc.py`, `vm.py`. A shared `NodeBase` would cut a few hundred lines;
  the missing `VM` proxmox gate is that drift already showing. Note `models/select.py:node_kind`
  relies on `isinstance` LXC → VM → host, which survives a shared base only if `VM` does not
  become a `Host` subclass.
- **`ip: IPv4Address`** — no IPv6 anywhere in the inventory, while `AccessList` accepts
  `IPvAnyNetwork` and the docs tell you to write `::/0`. Also means a `deny` on a host's v4
  address is bypassed if that host reaches the service over v6.
- **One address per node**, serving as both "where labops connects" and "what gets published".
  A node on both LAN and Tailscale cannot say so.
- **`remote_ip` vs `client_ip`** is addressed by ticket 4, but the related gap remains: no way
  to configure the 403 response, and a 403 confirms a hostname exists where a nonexistent one
  gets the fallback 404 — a small information leak.
- **Node-level `access:` inheritance** for a box exposing several services on one policy.
  Rejected on the grounds that one inherited attribute is worse than none, given tags
  deliberately do not inherit.
