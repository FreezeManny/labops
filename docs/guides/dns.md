# Pi-hole DNS

labops keeps your local DNS in step with your inventory by deriving one from the
other.

## There is no record list

Every host, VM and LXC in your config becomes a record:

```
<name><local_dns_suffix>  ->  <ip>
```

That is the whole model. You never write a record, which means DNS cannot drift
from the inventory — they are the same declaration. Move a service to another
machine and its name follows.

```yaml
settings:
  dns:
    local_dns_suffix: .lab      # a leading dot is optional
    pihole_location: pihole
    api_port: 8080

hosts:
  cprox:
    type: proxmox
    os: debian
    ip: 10.0.10.3               # -> cprox.lab
```

### A device that only needs a name

Something labops does not manage — a NAS, a printer, a switch — is written as an
ordinary node with `os: unmanaged`. It is then resolved and proxied like
everything else, but skipped by setup and update:

```yaml
  nas:
    type: bare-metal
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

`dns list` needs only `local_dns_suffix`. Records are derived before any network
access, so you can see exactly what would be published before you have a Pi-hole
to point at.

`sync` always prints its plan first, and asks for confirmation when records will
be deleted. `--yes` skips the prompt; `--dry-run` prints the plan and stops.

## Pointing at your Pi-hole

`pihole_location` accepts three different things, and which you write decides
what `labops dns upgrade` is allowed to do:

| You write | Records | `dns upgrade` |
| --- | --- | --- |
| A node in your config (name or IP) | ✅ | ✅ |
| A Docker stack name | ✅ — sent to the node running it | ❌ refuses |
| A bare IP matching nothing in the config | ✅ | ❌ nothing to reach |

It is one field rather than two because `sync` needs an address and `upgrade`
needs the thing behind that address — and they must not be able to disagree
about which Pi-hole is meant.

### The API password

Put it in the secret store, not the config:

```bash
# .env, next to homelab.yml and git-ignored
PIHOLE_PASSWORD=…
```

Use either the web-interface password or an app password from **Settings → Web
interface / API**. You *can* inline it as `settings.dns.password`, but that is
clear text in a file you probably commit, and `dns sync` warns about it.

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

To check without upgrading:

```yaml
settings:
  dns:
    upgrade_command: pihole -up --check-only
```

## See also

- [`settings.dns` reference](../configuration/dns.md) — every key
- [`labops dns` reference](../commands/dns.md) — every command
