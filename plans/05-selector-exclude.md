# Ticket 5 — `Selector.exclude`

**Breaking:** no (purely additive). **Depends on:** nothing. Can land any time.

## Why

`Selector` (`models/select.py`) has four positive filters — `kind`, `os`, `tags`, `under` —
combined as AND across fields and OR within a field. There is no way to subtract anything, so
"update everything except the Pi-hole" currently requires tagging every *other* node.

## Target usage

```yaml
settings:
  targets:
    weekly:
      kind: [vm, lxc]
      os: [debian]
      exclude: [pihole]        # new
```

```bash
labops update --all --exclude pihole
labops update --under cprox --exclude docker
```

## Scope

### 1. `models/select.py`

- Add `exclude: list[str] = Field([], …)` — node names. Like `under`, a name matches that
  node **and everything below it**, so excluding a Proxmox host drops its guests too.
- Apply it in `matches()` *after* the positive filters: a ref is excluded when
  `set(sel.exclude) & set(ref.path)` is non-empty. `ref.path` is the node path, which is what
  makes the subtree semantics fall out for free — the same mechanism `under` already uses.
- Include `exclude` in the existing `_to_list` `field_validator`, so `exclude: pihole`
  (a bare string) works like every other field.
- Extend `Selector.describe()` with `("--exclude", self.exclude)` so error output shows the
  flags that would reproduce the selection.
- Extend `Selector.is_empty` — decide deliberately: a selector with *only* `exclude` set is
  not empty (it means "everything but these"), so `is_empty` must account for it or
  `--exclude` alone will be treated as "no constraint given".
- `select_nodes` — reuse `unknown_under_names(hosts, sel.exclude)` for the typo check and
  raise the same `KeyError`. An unknown name must be an error, matching `under`'s existing
  rationale: a silent empty subtraction looks like success.

### 2. CLI

`src/cli/update.py` — an `--exclude` option alongside `--under`, multiple-valued, feeding
`Selector.exclude`.

### 3. Named target sets

`models/input_conf/yaml_root.py:235` (`validate_target_names`) currently checks only `under`:

```python
for missing in unknown_under_names(self.hosts, sel.under):
```

Extend it to `exclude` as well. The reason is in that validator's own docstring — a named set
is curated config run months later, so a typo in it is invisible: the selection quietly
matches the wrong thing and the run looks like a success.

## Tests

`tests/models/test_select.py`:

- `exclude` drops a named node
- `exclude` drops a node's whole subtree (exclude the Proxmox host → guests gone too)
- `exclude` combines with positive filters (AND: matches the filters *and* not excluded)
- a bare string coerces to a one-item list
- an unknown name raises, both ad-hoc and inside `settings.targets`
- `describe()` includes `--exclude`
- a selector with only `exclude` is not treated as "no constraint"

## Docs

`docs/guides/targets.md` (hand-written) — document `exclude`, the subtree semantics, and that
it is applied after the positive filters. The generated `docs/commands/update.md` picks up the
new flag automatically from Typer.

## Verification

```bash
just check && just test
labops update --all --exclude <node> --dry-run       # confirm the node and its guests are gone
labops update <named-set> --dry-run                  # a set carrying exclude
```

## Do not

- Do not add per-field negation (`--not-os`, `--not-tag`). Only node-name exclusion was
  scoped; a full negation grammar is a much larger design question.
- Do not make an unknown `exclude` name a silent no-op. It must raise, for the same reason
  `under` does.
