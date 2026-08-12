# Selecting targets

`labops update` acts on a **selection** rather than a single machine. This is
the command you reach for when the question is "patch the Debian containers" or
"everything under this Proxmox host", instead of naming nodes one at a time.

## The four filters

A selection is four optional filters, combined as **AND across filters, OR
within one**:

| Filter | Selects | Values |
| --- | --- | --- |
| `--kind` | The node's place in the tree | `host`, `vm`, `lxc` |
| `--os` | Its operating system | `debian`, `alpine`, `redhat`, `unmanaged` |
| `--tag` | A label you put on the node | anything |
| `--under` | A subtree | any node name |

So `--kind lxc --os debian` means *containers **and** Debian*, while
`--tag a --tag b` means *tagged a **or** b*.

```bash
labops update --kind lxc --os debian     # every Debian container
labops update --under cprox              # cprox and everything below it
labops update --tag prod --only stacks   # only the stacks on prod-tagged nodes
labops update --all --list               # preview everything, run nothing
```

A selection covers both the matching nodes *and* the Docker stacks running on
them. Narrow that with `--only nodes` or `--only stacks`.

!!! note "`--kind` is not a node's `type`"
    `--kind` is the node's position in the tree — host, VM or container. A
    node's `type` field is a different thing: the hardware kind, `bare-metal` or
    `proxmox`. The two are deliberately not named the same.

## Preview before you run

`--list` prints the resolved targets and exits:

```bash
labops update --tag prod --list
```

You do not have to remember to use it. Every run prints that same preview and
asks before proceeding — `--yes` skips the prompt for unattended use, and
`--dry-run` runs Ansible in check mode so nothing changes.

## Tagging

Tags are free-form labels on a node:

```yaml
hosts:
  cprox:
    tags: [prod, proxmox]
```

**Tags are local to the node that carries them.** A container under `cprox` is
not `prod` merely because its host is — it has to say so itself. This is
deliberate: inherited tags make it impossible to say "the host but not its
guests", and quietly widen a selection as the tree grows.

When you *do* want the whole subtree, that is what `--under` is for:

```bash
labops update --under cprox    # cprox, its VMs, its containers, their stacks
```

An `--under` name that matches nothing is an error, not an empty selection —
otherwise a typo would look exactly like a successful run with nothing to do.

## Saving a selection

A selection you run regularly belongs in the config, not in your shell history:

```yaml
settings:
  targets:
    weekly:                  # the debian guests patched on Sundays
      kind: [vm, lxc]
      os: [debian]
    edge:                    # the production side of cprox, containers included
      under: [cprox]
      tags: [prod]
    containers:
      kind: lxc              # a single value need not be a list
```

Then invoke it by name:

```bash
labops update weekly
labops update edge --dry-run
```

Named sets take the same four fields as the CLI options and combine them the
same way. An empty field means "no constraint", so a set with only `kind: [lxc]`
is every container regardless of OS, tags or position.

## How a run executes

Behind one command, labops performs up to three sequential Ansible runs: nodes
reached over SSH, then containers reached with `pct`, then Docker stacks. They
cannot share an inventory — a container has no SSH endpoint, and a stack is
addressed through its node — so they are separate phases rather than one big
play.

The practical consequence is that the preview groups targets the same way, and a
failure in one phase is reported against that phase.

## See also

- [`labops update` reference](../commands/update.md) — every flag
- [Selector configuration](../configuration/settings.md#selector) — the fields of a named set
