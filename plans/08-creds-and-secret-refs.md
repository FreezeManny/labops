# Ticket 8 — `creds.password`, consistency fixes, secret references

**Breaking:** yes. **Depends on:** ticket 2 (validation context — though the `env_file` part
of that work lives in ticket 2 itself) and ticket 7 (`Dns.password` → `Pihole.password`).

Run the two phases in order: phase A renames `Creds.passwd`, phase B changes that same
field's type. Doing B first means re-typing a field you are about to rename.

---

## Phase A — consistency fixes

Four unrelated small fixes, each self-contained.

### A1. `Creds.passwd` → `password`

`models/input_conf/creds.py:19-33`. Straight rename, **no alias** — the clean-break decision
rules out `AliasChoices`/`populate_by_name`, which would be the first in this codebase.
Motivation: `Creds` says `passwd` while `Dns` says `password` for the same concept.

Update:
- the two mutual-exclusion messages at `:49` and `:53`
- `src/utils/inventory.py:35-39` (`ssh_host_vars` → `ansible_password` **and**
  `ansible_become_password`) and `:56-59` (`pct_host_vars` → `ansible_password` only,
  deliberately no become password)

### A2. `Settings.default_creds` optional

`models/input_conf/settings.py:21-26` — currently required, so a render-only or DNS-only
config must invent SSH credentials it never uses.

Make it `Optional[Creds]`, and add a **`YamlRoot` model validator** requiring it only when some
managed node (`os != "unmanaged"`) has no `creds` of its own. It has to live on `YamlRoot`
because `Settings` cannot see the host tree.

Consumers to check for `None` handling: `src/docker/find.py:33-35`, `src/host/setup.py:21`,
`src/docker/common.py:29`, `src/utils/target.py:70` (LXCs use the **parent's** creds).

### A3. `Docker.root_path` must be absolute

`models/input_conf/docker.py:52-58` is a bare unvalidated `str`, while the analogous
`ProxyDeploy.caddyfile_dest` is checked. Both are resolved on the *target*, so a relative value
lands in the remote SSH login directory.

Copy the existing pattern verbatim — `ProxyDeploy.validate_caddyfile_dest_absolute`
(`models/input_conf/proxy.py:154-164`) uses `PurePosixPath(...).is_absolute()`, which is the
right choice because the check is about the target's filesystem, not the control machine's.

`root_path` reaches Ansible only via `src/docker/common.py:41`
(`f"{result.docker_root.rstrip('/')}/{result.stack.name}"` → `compose_dest`), used purely as a
remote path. Trailing slashes are tolerated by that `rstrip` and should stay tolerated.

### A4. `Host.name` semantics

`models/input_conf/host.py:29-35` documents the field as *"Filled in from the key this node is
written under; do not set it."* — but it is an ordinary field, a user **can** set it, and
`validate_unique_names` (`yaml_root.py:114`) deliberately checks *effective* names. Meanwhile
`VM.name` and `LXC.name` document the same field positively as an override.

Settle it as an override on all three, and align the `Host.name` docstring with the other two.
Do not change behaviour — `propagate_host_names` (`yaml_root.py:59`) and
`Host.propagate_lxc_vm_names` (`host.py:161-173`) already fill only the blanks.

### A5. Add the missing `VM` proxmox gate

`Host` has `check_proxmox_support` (`models/input_conf/host.py:123-130`), which rejects `lxc:`
or `vm:` blocks unless `type: proxmox`. `VM` carries the same `type: HostType` field
(`models/input_conf/vm.py:35`) and the same nested `lxc:`/`vm:` blocks, but **has no equivalent
validator** — so `type: bare-metal` plus a nested `lxc:` block errors on a Host and validates
silently on a VM.

Add the same check to `VM`. The natural home is
`models/input_conf/common_validators/`, alongside `managed.py` and `web_services.py`, so the
rule lives in one place for both classes rather than being copied.

Phrase the condition as `type == "proxmox"` rather than `type != "bare-metal"`. `lxc:` is
Proxmox-specific — `pct_host_vars` sets `ansible_connection:
community.proxmox.proxmox_pct_remote` — so if `HostType` ever gains a third hypervisor it must
not inherit LXC support by default. Equivalent today, forward-safe tomorrow.

This is the drift that the deferred `NodeBase` refactor would prevent (see
`plans/README.md` → Deferred); fixing the symptom here is cheap and does not depend on it.

### A6. `type` → `hypervisor`

`Host.type` / `VM.type` (`HostType = Literal["bare-metal", "proxmox"]`,
`models/input_conf/custom_types.py:14`) is not really a "type" — it answers *does this node
virtualize, and with what*. Two consequences of the current naming:

- **`type: bare-metal` is a false statement on a VM.** `VM` carries the same field with the
  same default (`vm.py:35-36`), so every virtual machine claims to be bare metal unless it is a
  nested Proxmox node.
- **It collides with the selector's `kind`.** `models/select.py:29-31` carries a comment
  explaining that `NodeKind` is "deliberately *not* named `type`" because `Host.type` already
  means the hardware kind, and "two different meanings for one word in one YAML file is a
  support question waiting to happen". `docs/guides/targets.md:32-34` is a whole admonition
  written to defuse that same collision.

Rename the field to `hypervisor`, values `none | proxmox`, default `none`:

```yaml
nas:
  hypervisor: none        # was type: bare-metal   (now true)
cprox:
  hypervisor: proxmox     # unlocks lxc: / vm:
fr24-radar:
  # omitted -> none                                (was a lie)
```

Every value becomes true, the `kind`-vs-`type` collision disappears, and a second hypervisor
reads naturally (`hypervisor: vmware`) when one lands.

**Code surface** — `.type` is read in only three places, and no logic anywhere depends on
`"bare-metal"` meaning "physical hardware":

- `models/input_conf/custom_types.py:14` — `HostType` → `Hypervisor`, values `none | proxmox`
- `models/input_conf/host.py:11,33-40` and `models/input_conf/vm.py:10,35-41` — the field, its
  import, and its description
- `models/input_conf/host.py:123-130` — `check_proxmox_support`, which becomes
  `hypervisor == "proxmox"` (see A5)
- `src/cli/host.py:102` — `str(h.type)` in the `host list` table; header becomes `Hypervisor`
- `src/cli/vm.py:111` — renders `str(v.type) + " (in VM)"`; review what that column should say
  once most rows read `none`
- `models/select.py:29-31,50` — simplify the comment and the `kind` field description; the
  collision they work around is gone

**Tests:** `tests/models/test_custom_types.py` (its docstring names `HostType`, and it tests
literal rejection), `tests/models/test_host.py:19,28,84`, `tests/conftest.py:92,98`,
`tests/dns/test_location.py:107`, `tests/src/test_host_update.py:30`.

**Docs** — wider than the rest of this ticket, because the key appears in both front-page
teasers: `README.md:14`, `docs/index.md:13`, `docs/getting-started.md:91,98`,
`docs/guides/dns.md:27,40`, `docs/guides/docker.md:12`, `docs/guides/proxy.md:29`,
`docs/guides/wake.md:30`, `docs/guides/targets.md:32-34` (the admonition can shrink a lot), and
`docs/gen_docs.py:131` (the nodes-page intro, hand-written prose inside the generator).

**⚠ Do not blanket-replace the string `bare-metal`.** Most occurrences are ordinary English
describing physical machines and stay correct: `src/cli/host.py:3,23`, `src/utils/target.py:55`,
`src/utils/inventory.py:7`, `src/host/update.py:23`, `src/cli/wake.py:6`, `src/wake/find.py:5`,
`docs/guides/wake.md:11`, and a long tail of test docstrings and function names
(`test_a_bare_metal_host_gets_a_local_packet`, etc.). Only **config key values** change.

One cross-ticket note: `models/input_conf/dns.py:21` documents a DNS-only device as
"``type: bare-metal``, ``os: unmanaged``". Ticket 7 rewrites that docstring anyway — if 7 has
already landed, fix the wording here; if not, 7 should write it as `hypervisor: none`.

---

## Phase B — secret references

### The rule

`${VAR}` in a secret field is a **reference**, not substitution: it names which env var holds
the secret. The built-in names stay as defaults, so `${VAR}` is purely an override.

| Field | Default source | With `${MY_VAR}` |
| --- | --- | --- |
| `dns.pihole.password` | `PIHOLE_PASSWORD` in the secret store | reads `MY_VAR` instead |
| `proxy.tls.token` | rendered as `{env.CF_API_TOKEN}` for Caddy | rendered as `{env.MY_VAR}` |
| `creds.password` | none — inline only today | resolved at inventory-build time |

The secret store is the `.env`-style file located by `resolve_env_file`
(`src/utils/env_file.py:10-22`). **The process environment is deliberately not consulted** —
that matches how `PIHOLE_PASSWORD` works today. (Confirmed: there is currently no `os.environ`
read anywhere in the tracked tree.)

### B1. New `src/utils/secrets.py`

`is_secret_ref(v)`, `ref_name(v)`, `resolve_secret_ref(v, secrets) -> str | None`. Reuses
`read_env_file` / `resolve_env_file`.

### B2. A `SecretRef` annotated `str` in `models/input_conf/`

Validates only the **syntax** — `${NAME}` with a legal env var name — and stores the value
verbatim. Applied to `Pihole.password`, `ProxyTls.token`, `Creds.password`. Resolution never
happens at validation time.

### B3. Pi-hole password — `src/dns/sync.py`

`resolve_password` (`:38-51`): a ref → look up that name; inline → use it; unset → fall back to
`PIHOLE_PASSWORD`. Today's missing-password case is a hard `ValueError` (`:44-51`) — keep that.

`dns_warnings` (`:54-68`) currently warns whenever `dns.password` is set at all, on the grounds
that it is an inline secret. A ref is **not** an inline secret, so it must not trip that warning.

### B4. TLS token — `src/proxy/render.py`

`_tls_lines` (`:75-82`) is the interpolation point:

```python
secret = token if token is not None else f"{{env.{spec.token_env}}}"
return [f"dns {spec.caddy_module} {secret}"]
```

Becomes three cases: a ref renders `{env.<NAME>}`; inline renders the literal; unset falls back
to `{env.<spec.token_env>}`. **A ref must never be resolved into the Caddyfile** — the whole
point is that Caddy resolves it from its own container environment at runtime, so the secret
never lands in a file that gets copied to the proxy node.

`tls_warnings` (`:85-137`) has three cases today — inline set / neither set / both set but
differing — and needs a fourth-state-aware rewrite so a ref is treated as "not inline".

### B5. SSH password — `src/utils/inventory.py`

Resolve a `creds.password` ref **here**, at inventory-build time (`:35-59`), not at load time.
Reason: `ansible-runner` serialises the inventory to
`.ansible-autogenerate/inventory/hosts.json` (`src/utils/ansible_runner.py:236-254`), so
keeping the plaintext off the model keeps it out of anything that serialises the model.

Both `ssh_host_vars` and `pct_host_vars` need the secret store threaded in. Callers to update:
`src/docker/common.py:32`, `src/host/update.py:46`, `src/lxc/update.py:47`,
`src/wake/run.py:91`, and `src/utils/target.py:75,86,96` (which feeds `resolve_node_host_vars`
→ `src/proxy/deploy.py:26`).

Note `src/host/setup.py:45-73` builds host_vars with interactively-prompted passwords via
`getpass`, not from config — leave it alone.

## Tests

Phase A:
- `tests/models/test_creds.py:14,19-31` — **attribute** reads of `creds.passwd` (input-side
  dicts in `tests/src/test_docker_common.py:25`, `test_host_update.py:25`,
  `test_docker_find.py:69`, `tests/wake/test_wake_run.py:200` also need renaming)
- new: `root_path` rejects a relative value (all existing fixtures use `/srv`, so nothing
  breaks — add the negative test)
- new: `default_creds` omitted with an all-unmanaged config validates; omitted with a managed
  node lacking `creds` is rejected

Phase B — new tests for each of the three fields:
- `${VAR}` syntax accepted, malformed rejected
- `dns.pihole.password: ${MY_VAR}` reads `MY_VAR` from the secret store; unset still falls back
  to `PIHOLE_PASSWORD`; a ref does not trigger the inline-secret warning
- `tls.token: ${MY_VAR}` renders `dns cloudflare {env.MY_VAR}` — assert the literal value never
  appears in the output
- `creds.password: ${MY_VAR}` resolves in the built inventory, and the model still holds the
  `${…}` reference

Existing tests that pin the hardcoded names must keep passing (defaults are unchanged):
`tests/proxy/test_tls_providers.py:29` (`token_env == "CF_API_TOKEN"`),
`tests/proxy/test_render.py:54` (`"dns cloudflare {env.CF_API_TOKEN}"`),
`tests/models/test_dns.py:105` (`PIHOLE_PASSWORD_ENV`), `tests/proxy/test_tls_warnings.py`,
`tests/dns/test_sync.py`.

## Docs

- `docs/getting-started.md:183-195` — "Keep secrets out of the config", including the `.env`
  block at `:188-192`. Rewrite for `${VAR}`.
- `docs/guides/dns.md` — the API password section (`:93-104`), and the "One instance only"
  reasoning (`:106-112`) which rests on the single hardcoded `PIHOLE_PASSWORD`; `${VAR}` weakens
  that constraint but the one-instance limit stays for other reasons.
- `docs/guides/proxy.md` — the TLS token section, noting `${VAR}` becomes a Caddy `{env.…}`
  reference.
- `docs/guides/docker.md:35` — add that `root_path` must be absolute.

## Verification

```bash
just check && just test
labops proxy render | grep 'dns cloudflare'   # must show {env.…}, never a literal token
labops update --all --dry-run
grep -r '\${' .ansible-autogenerate/inventory/hosts.json   # must find nothing
```

## Do not

- Do not add an alias for `passwd`. Clean break, decided.
- Do not resolve `${VAR}` for `tls.token` into the rendered Caddyfile. It must stay a Caddy
  `{env.…}` reference — that was the explicit decision, and it preserves today's property that
  the secret never reaches disk.
- Do not resolve `creds.password` at load time. Considered and declined: it would put plaintext
  on the model for the whole run.
- Do not give `creds.password` an implicit default env var name. There is no sensible single
  name for per-node credentials; `${VAR}` is the only form.
- Do not consult `os.environ`. The secret store is the only source, matching today's behaviour.
- Do not extend `${VAR}` to `reload_command` / `upgrade_command` or any other string field.
  Those are shell strings run on the remote, where `${VAR}` may be intended for the *remote*
  shell. Secret fields only.
