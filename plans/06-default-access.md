# Ticket 6 — `default_access` + reject deny-carrying unions

**Breaking:** yes — every config with a proxy must be edited.
**Depends on:** nothing, but do **ticket 3** first so `proxy access` can verify no resolved
CIDR set changed.

## Why

Two separate problems in `models/input_conf/proxy.py`.

**1. `default: true` is a flag where a key belongs.** Each `AccessList` carries
`default: bool`, and a `Proxy` model validator (`validate_access_lists`, `:240-254`) then has
to enforce "exactly one list sets it" — rejecting both zero and two. A single field naming the
default makes both failure modes unrepresentable instead of validated.

**2. `deny` leaks across unioned lists.** `_resolve_acl` (`src/proxy/render.py:46-60`) unions
both `accept` **and** `deny` across every list a service names. So `access: [local, vpn]`
applies `local`'s LAN-scoped `deny: [10.0.10.66/32]` to tailscale clients arriving via `vpn` —
a deny that was a statement about LAN policy silently becomes a global ban on that route.

## Target config

```yaml
settings:
  proxy:
    proxy_suffix: .example.com
    default_access: local        # new; required
    access_lists:                # stays required
      local:
        accept: [10.0.10.0/24]   # `default: true` gone
        deny:   [10.0.10.66/32]
      vpn:
        accept: [100.64.0.0/10]
```

## Scope

### 1. Model changes

- **Remove `AccessList.default`** (`proxy.py:17-23`). `validate_accept_non_empty`
  (`:41-45`) stays — a list must still have at least one `accept` CIDR.
- **Add `Proxy.default_access: str`**, required. A model validator replacing
  `validate_access_lists` (`:240-254`) checks the value is a key of `access_lists`; the error
  names the bad value and lists the valid keys.
- **Delete the `default_access_list` property** (`:257-259`) and update its two readers:
  - `src/proxy/render.py:53` — inside `resolve_acl` (named `_resolve_acl` before ticket 3)
  - `src/cli/proxy.py:112` — `default_list`, which feeds `_access_label` (`:59-62`) and
    renders the `… (default)` marker in `proxy list`'s Access column

### 2. Reject deny-carrying unions

Extend `validate_access_references` (`models/input_conf/yaml_root.py:257-291`) — it already
iterates `iter_web_services()` and holds `known_lists`, so both checks belong there:

- **Name the node** in the existing unknown-list error. It currently identifies the service by
  `proxy_name` (or its port when it has none) but not where it lives; the `WebServiceRef`
  already carries `.path`, so use it.
- **New error:** when a service names more than one list and any of them has a non-empty
  `deny`, reject. Message must name the service, its node path, which list carries the deny,
  and say the remedy is a purpose-built list. `default_access` names a single list, so it is
  unaffected.

### 3. Stale comments

- `models/proxy/route_result.py:13-15` — the comment
  `# access-list names (union); None -> local; ["public"] -> open` hardcodes list names that
  were never guaranteed.
- `models/input_conf/yaml_root.py:285` — "Configure settings.proxy (proxy_suffix,
  access_lists)" is still accurate since `access_lists` stays required; check it reads well
  next to the new `default_access`.

### 4. No template change

`ansible/files/proxy/Caddyfile.j2` is untouched. Both matchers are already `{% if %}`-guarded,
and under this design `accept` is never `None` — `access_lists` is required, `default_access`
always names a real list, and every list has ≥1 accept CIDR.

## Tests

**Do `tests/conftest.py:56` first** — it holds
`"access_lists": {"local": {"default": True, "accept": ["10.0.0.0/24"]}}` and unblocks every
downstream file. Then:

| File | What breaks |
| --- | --- |
| `tests/models/test_proxy.py:25,34,44-72` | `_proxy` fixture; `test_proxy_requires_a_default_list` matches the literal `"exactly one list as 'default: true'"`; `test_proxy_rejects_multiple_defaults`; `default_access_list` assertion at `:34`; `AccessList` block at `:230-253` asserts `al.default is False` |
| `tests/models/test_settings.py:54` | fixture |
| `tests/models/test_proxy_access.py:36-62` | adds a second list with no `default` |
| `tests/proxy/test_render.py:140,155,167` | list definitions; `test_render_default_access_is_local_remote_ip` at `:129` |
| `tests/src/test_docker_find.py:73` | fixture |

New tests: `default_access` naming an unknown list is rejected; a two-list `access` where one
carries `deny` is rejected; a two-list `access` where neither does is accepted; the
unknown-list error names the node.

## Docs

- `docs/guides/proxy.md:17-35`, `:62-80`, and `:97-98` ("Exactly one list must be marked
  `default: true` — a service with no explicit `access` has to resolve to something").
  Also document the new multi-list-with-deny restriction.
- **Leave the IPv6 admonition at `:100-102` in place and make sure it survives.** It is now
  the only place that trap is documented, since `test-samples/homelab-complete.yml` (which
  carried the same warning in a comment) is deleted in ticket 1.
- `docs/getting-started.md:162-165` — the `access_lists` / `default: true` snippet.
- `docs/editor-setup.md:103-110` — claims the schema checks *"that exactly one access list is
  the default"*. Now wrong; `default_access` is a plain string reference.
- `ansible/files/proxy/README.md:27-32` (example config with `default: true` at `:31`) and
  `:179-180` (the `accept`/`deny` row descriptions referencing "the default list").

## Verification

```bash
just check && just test
labops proxy access      # compare against the pre-change output — CIDR sets must be identical
labops proxy render      # matchers must be byte-identical to before
```

## Do not

- Do not make `access_lists` optional. Considered and declined: omitting it would make every
  route unrestricted, one forgotten block away from an open proxy.
- Do not add `default_access: none` or `access: none`. Explicitly rejected — "none" reads as
  "no access" but would mean "no restriction". A service resolves to the default list or to
  named lists, nothing else.
- Do not add `accept: any`. Also declined: `[0.0.0.0/0, ::/0]` remains how "public" is
  written.
- Do not "fix" the deny union by computing per-list `accept − deny` with
  `ipaddress.address_exclude`. It is the semantically correct fix, but excluding a /32 from a
  /24 expands to ~8 prefixes and the rendered Caddyfile gets much noisier. Rejecting the
  ambiguous config is the chosen approach.
- Do not add a warning for `0.0.0.0/0` without `::/0`. Considered and declined; it stays
  documented only.
