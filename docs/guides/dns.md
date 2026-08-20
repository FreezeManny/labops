# Pi-hole DNS

labops keeps your local DNS in step with your inventory by deriving one from the
other.

## There is no record list

Every host, VM and LXC in your config becomes a record:

```
<name>.<suffix>  ->  <ip>
```

That is the whole model. You never write a record, which means DNS cannot drift
from the inventory — they are the same declaration. Move a service to another
machine and its name follows.

```yaml
settings:
  dns:
    suffix: .lab                # a leading dot is optional
    pihole:
      target: pihole            # the machine running Pi-hole
      port: 8080

hosts:
  cprox:
    hypervisor: proxmox
    os: debian
    ip: 10.0.10.3               # -> cprox.lab
```

### A device that only needs a name

Something labops does not manage — a NAS, a printer, a switch — is written as an
ordinary node with `os: unmanaged`. It is then resolved and proxied like
everything else, but skipped by setup and update:

```yaml
  nas:
    os: unmanaged
    ip: 10.0.10.4               # -> nas.lab
```

### Renaming and excluding

```yaml
  fr24-radar:
    dns_name: fr24              # -> fr24.lab, not fr24-radar.lab

  homeassistant-os:
    dns_name: [hass, ha]        # several labels -> one address

  tmp-pi:
    dns: false                  # scratch box: tracked, never published
```

!!! warning "Node names are DNS labels"
    Once `settings.dns` is configured, a node's name has to be a legal DNS
    label — no underscores. A node with an explicit `dns_name` is exempt, since
    its own name is never published.

## The commands

```bash
labops dns list      # what the config implies      (no network)
labops dns diff      # config vs. what Pi-hole has  (changes nothing)
labops dns sync      # make Pi-hole match           (asks before deleting)
```

`dns list` needs only `suffix`. Records are derived before any network
access, so you can see exactly what would be published before you have a Pi-hole
to point at.

`sync` always prints its plan first, and asks for confirmation when records will
be deleted. `--yes` skips the prompt; `--dry-run` prints the plan and stops.

## Pointing at your Pi-hole

Pi-hole is one *backend*. Deriving records from the inventory, diffing them and
rendering the plan know nothing about it — a `pihole:` block is what says "publish
them there", and `settings.dns` carries one server block at a time. If labops
learns to speak to another DNS server, everything above this section stays as it
is and only the block changes.

### Naming the machine

The `pihole:` block takes exactly one of two keys, and which one you write decides
what `labops dns upgrade` is allowed to do:

| You write | Means | Records | `dns upgrade` |
| --- | --- | --- | --- |
| `target: pihole` | the machine it is installed on — a host, VM or LXC, by name or IP | ✅ | ✅ |
| `target: pihole` where that node is `os: unmanaged` | a Pi-hole labops publishes to but does not manage | ✅ | ❌ labops runs no commands on it |
| `docker_stack: pihole` | the docker stack running it | ✅ — sent to the node hosting it | ❌ pull a new image instead |

`target:` must name a node in this config. A Pi-hole labops does not otherwise
manage is declared like any other node with `os: unmanaged` (see
[A device that only needs a name](#a-device-that-only-needs-a-name) above) rather
than named by a bare address — records work either way, and declaring it keeps the
machine inside the duplicate-IP and DNS-label checks instead of outside them.

`target:` is the same lookup as `settings.proxy.deploy.target`, so an LXC needs no
sshd — it is reached with `pct` through its Proxmox parent, and a Pi-hole in an LXC
is named directly.

Both keys are checked when the config loads, not when you first run `dns sync`: a
`target:` that names no node, or a `docker_stack:` that names no stack — or names
one that exists on two nodes — fails the load with the same message the command
would have printed. A field you write once and read months later is exactly the one
a typo hides in.

Where Pi-hole is stays a single answer rather than an address plus a machine,
because `sync` needs an address while `upgrade` needs the thing behind that
address — and the two must not be able to disagree about which Pi-hole is meant.
What the two keys split out is whether Pi-hole is *installed on* a machine or
*running in a container on* one, which is the one thing an address cannot tell you:
a container and an installation answer at the same IP. So labops never infers it. A
node and a stack may share a name, a typo in `target:` is an error rather than a
silent fallthrough to the stacks, and the Docker refusal is something you declared
rather than something labops guessed.

### Scheme and port

```yaml
    pihole:
      target: pihole
      scheme: https        # port becomes 443
```

`port:` defaults to whatever the scheme implies — 80 for `http`, 443 for `https` —
so switching to `https` needs no second field. Set it explicitly for a Pi-hole on
an unusual port; an explicit value always wins. `https` skips certificate
verification, since Pi-hole's own certificate is self-signed.

### The API password

Put it in the secret store, not the config:

```bash
# .env, next to homelab.yml and git-ignored
PIHOLE_PASSWORD=…
```

Use either the web-interface password or an app password from **Settings → Web
interface / API**. You *can* inline it as `settings.dns.pihole.password`, but that
is clear text in a file you probably commit, and `dns sync` warns about it.

### One instance only

There is no list of Pi-holes. The secret store holds a single password, so a list
would quietly assume they all share it. With a replicating setup
([nebula-sync](https://github.com/lovelaze/nebula-sync)), point labops at the
primary and let it propagate to the rest.

## Upgrading Pi-hole itself

```bash
labops dns upgrade
```

This is the one operation with no API behind it, so it goes over SSH — or `pct`
when the Pi-hole is an LXC.

It exists as its own command because **`host update` and `lxc update` do not
cover Pi-hole.** Those run the package manager, and Pi-hole installs from its own
installer, so apt never sees it. Without this command a Pi-hole would sit at an
old version through every routine patch run.

Bare installs only. A containerised Pi-hole is upgraded by pulling a new image
(`labops docker stack update`), and `dns upgrade` refuses that case rather than
pretending to have done something.

## See also

- [`settings.dns` reference](../configuration/dns.md) — every key
- [`labops dns` reference](../commands/dns.md) — every command
