# Ticket 7 — `settings.dns` restructure

**Breaking:** yes — every config with a `dns:` block must be edited.
**Depends on:** nothing. **Must land before phase B of ticket 8**, which targets
`Pihole.password` at its new address.

The largest single ticket: it rewrites `src/dns/location.py` and most of `tests/dns/`.

## Why

Two problems in `models/input_conf/dns.py`.

**1. The block is Pi-hole-specific but not namespaced.** `api_port`, `api_scheme`,
`password` and `upgrade_command` are all Pi-hole implementation details sitting beside the
one vendor-neutral key, `local_dns_suffix` — while `pihole_location`, the one key that *is*
prefixed, is the odd one out. Nesting them leaves room for a second DNS backend later.

**2. `pihole_location` is one string overloaded four ways** — node name, IP, vmid, or docker
stack name — and `src/dns/location.py` resolves it by *guessing*: try nodes, then stacks, then
parse as an IP, and raise if a name matches both a node and a stack. The existing docstring
defends one field over two on the grounds that `sync` needs an address while `upgrade` needs
the thing behind it, and two fields could disagree. That argument is sound and is preserved —
the fix is to make the *kind* explicit rather than splitting the location in two.

`local_dns_suffix` → `suffix` is a pure stutter fix (`settings.dns.local_dns_suffix`), bundled
here because it touches the same model and tests.

## Target config

```yaml
settings:
  dns:
    suffix: .lab            # was local_dns_suffix; leading dot still optional
    pihole:                 # new nested block, optional
      node: pihole          # xor stack: / address: — exactly one
      port: 8080            # was api_port
      scheme: http          # was api_scheme
      password: xxxx
      upgrade_command: pihole -up
```

Which key you use still decides what `dns upgrade` may do, exactly as today:
`node:` supports everything; `stack:` refuses to upgrade (a container is upgraded by pulling
an image); `address:` has nothing to SSH into.

## Scope

### 1. Models (`models/input_conf/dns.py`)

- New `Pihole(StrictModel)`: `node` / `stack` / `address` with a model validator enforcing
  **exactly one**, plus `port` (default 80), `scheme` (`Literal["http","https"]`, default
  `http`), `password`, `upgrade_command`. Keep `DEFAULT_UPGRADE_COMMAND` and its non-empty
  validator. The old `_reject_blank` field validator on `pihole_location` (`:87-93`) is
  subsumed by the exactly-one check.
- `Dns` keeps `suffix: str` + `pihole: Optional[Pihole]`.

  **The rename collides with an existing member:** `Dns.suffix` is today a `@property`
  (`:104-111`) returning `local_dns_suffix.lstrip(".")`. Resolve it by normalizing at parse
  time — a `field_validator` on `suffix` that strips the leading dot — and **deleting the
  property**. `.suffix` then keeps identical semantics for every reader, of which there is
  exactly one in production: `src/dns/find.py:27` (`hostname=f"{label}.{dns.suffix}"`).
- Rewrite the class docstring. It currently contains three paragraphs arguing for the design
  being replaced.

### 2. Rewrite `src/dns/location.py`

`resolve_location` stops guessing and dispatches on which key is set:

| Key | Behaviour |
| --- | --- |
| `node:` | `resolve_target(config, v, "settings.dns.pihole.node")`; `TargetNotFound` is now a **hard error**, not a fallthrough |
| `stack:` | `find_stacks(config, stack_name=v)`; **distinguish** not-found from ambiguous — both are `KeyError` today and get collapsed into one generic message |
| `address:` | used directly |

The node-vs-stack ambiguity check (`location.py:100-105`) **disappears** — the user has said
which they meant. The `SETTING` module constant becomes per-branch strings.

Keep `PiholeLocation` and its `is_stack` / `where` / `address` / `target` surface intact, so
`src/dns/upgrade.py:49-67` needs only field-path edits rather than a rewrite.

Background on the two helpers this calls:

- `resolve_target(config, target, setting) -> ResolvedTarget` (`src/utils/target.py:51`)
  tries LXC → VM → host, matching by name, IP, and vmid for LXCs. Raises `TargetNotFound`
  (a `ValueError` subclass) when nothing matches. Ambiguity propagates as `KeyError` from the
  finders.
- `find(config, stack_name=…)` (`src/docker/find.py`) raises `KeyError` both for
  `"Stack 'x' was not found."` and for `"Stack 'x' exists in multiple locations: …"`.

### 3. Field-path updates

- `src/dns/sync.py:39-66` (`resolve_password`, `dns_warnings`) and `:86-87` (`scheme`/`port`
  into `PiholeClient`)
- `src/dns/upgrade.py:85` — `extravars={"pihole_upgrade_command": dns.upgrade_command}`
- `src/cli/dns.py:93` and `:217` — two direct `dns.pihole_location` prints; render via
  `PiholeLocation.where` instead

### 4. Message text naming old keys

`src/dns/sync.py:30` (`require_dns`), `src/dns/find.py:21-22`, `src/dns/pihole.py:137` and
`:224` (the latter is pinned by `tests/dns/test_pihole.py:262`, which matches the literal
`"pihole_location"`), `src/cli/dns.py:4,134,158,224`.

The setting name is also passed as a **string argument** into hostname errors — update
`models/input_conf/common_validators/dns.py:42` and `models/input_conf/yaml_root.py:192`, both
of which pass `"settings.dns.local_dns_suffix"` to `validate_hostname_label`.

### 5. Collapse a duplicated check

`src/dns/find.py:18-23` re-implements `require_dns`'s "settings.dns is not configured" check
with its own wording. Collapse to one.

### 6. Docs generator

**`docs/gen_docs.py:99` must gain `"Pihole"`** in the `dns.md` model list, or the new model is
silently undocumented (no `$defs` link target, so `link_to` degrades to a bare code span).
`:88` and `:93` carry hand-written prose in the generator itself, including
`` `<name><local_dns_suffix> -> ip` ``.

### 7. Opportunistic fixes in files being touched

- `ansible/playbooks/dns/upgrade.yml:13,17` — comments reference `settings.dns.upgrade.targets`
  and `settings.dns.upgrade.command`, keys that have never existed.
- `src/utils/target.py:4` references a nonexistent `settings.dns.target`; `:33` references
  `pihole_location`.

## Tests

**Do `tests/conftest.py:114-119` first** — the `dns_config_dict` fixture writes
`local_dns_suffix` and `pihole_location`, and six test modules depend on it. Note its default
is a bare off-config IP (`10.0.0.53`), which `test_upgrade_of_an_off_config_ip_exits_cleanly`
relies on → becomes `address:`.

Largely rewritten:

- `tests/models/test_dns.py` — the whole file is the old block's contract. `:43-78` are
  `pihole_location` shape tests; `:133-145` assert exactly the field-vs-property distinction
  being collapsed (`test_suffix_strips_a_leading_dot` and
  `test_local_dns_suffix_is_preserved_verbatim`). Also imports `PIHOLE_PASSWORD_ENV` at `:13` —
  keep that constant in this ticket (ticket 8 owns it).
- `tests/dns/test_location.py` — its whole premise is "one field, three shapes"
  (`:32-57` node by name/ip/vmid, `:63-76` stack, `:83-89` bare IP, `:95-150` failures
  including the node+stack ambiguity that no longer exists).

Field-path edits: `tests/dns/test_upgrade.py:47-50,73,80-82`,
`tests/dns/test_sync.py:33-41,52`, `tests/dns/test_cli.py:54-56,78,341-435`,
`tests/dns/test_find.py:31,36`, `tests/dns/test_pihole.py:262`,
`tests/models/test_settings.py:50,58`.

## Docs

`docs/guides/dns.md` is the heaviest edit in the whole refactor:

- `:11` — `<name><local_dns_suffix> -> <ip>`
- `:18-30` — the settings example
- `:71` — "`dns list` needs only `local_dns_suffix`"
- **`:78-91`** — "Pointing at your Pi-hole": the three-row shapes table plus the paragraph
  "It is one field rather than two because…". This prose *argues for* the design being
  replaced; rewrite it, don't patch it. The one-field rationale still holds — say that the
  kind is now explicit rather than inferred.
- `:93-112` — the API password and "One instance only" sections
- `:133-138` — the `upgrade_command` example

Also `docs/getting-started.md:142-143`.

## Verification

```bash
just check && just test
just docs-gen        # MUST NOT KeyError — this is the ticket that adds a model
just docs-build
labops dns list      # works with only `suffix` set
labops dns diff      # exercises each of node: / stack: / address:
```

`docs.yml` only runs on `release: published`, so `just docs-gen` locally is the only guard
against the `PAGES`/model mismatch. Run it before merging.

## Do not

- Do not split the location into two fields (`pihole_address` + `pihole_node`). The original
  one-field rationale stands: `sync` needs an address and `upgrade` needs the thing behind it,
  and two fields could disagree about which Pi-hole is meant.
- Do not support a list of Pi-holes. Still one instance; with a replicating setup
  (nebula-sync) point labops at the primary.
- Do not add deprecation aliases or a migration error for the old keys. Explicitly declined —
  `extra="forbid"` producing "Extra inputs are not permitted" is the accepted UX.
- Do not add a top-level `version:` key. Also declined.
- Do not do the `${VAR}` secret work here. That is ticket 8 phase B; leave
  `Pihole.password` as a plain optional string and keep `PIHOLE_PASSWORD_ENV` working
  exactly as it does today.
