# Getting started

## Install

```bash
pipx install labops
```

`labops` is a standalone CLI tool, so [pipx](https://pipx.pypa.io/) is
recommended — it keeps its dependencies isolated from the rest of your system.
`pip install labops` works if you prefer.

Check it landed:

```bash
labops --help
```

## Write a minimal config

Create `homelab.yml` in a directory of your choosing — a git repository is a good
home for it, since it is the record of your lab.

```yaml
settings:
  default_creds:
    username: root
    ssh_key_path: ~/.ssh/id_ed25519

hosts:
  nas:
    os: debian
    ip: 10.0.10.4
```

That is a complete, valid config. `settings.default_creds` and one node are all
labops needs.

!!! tip "Let your editor help"
    labops publishes a JSON Schema, so your editor can complete these keys and
    flag mistakes as you type. One line at the top of the file turns it on — see
    [Editor setup](editor-setup.md).

## Check it

```bash
labops validate
```

You do not pass a path. labops walks up from your current directory looking for
`homelab.yml` (or `homelab.yaml`), the way `docker compose` finds a compose
file — so you can run it from anywhere inside your config repository. Use
`--file` to point somewhere else explicitly.

Validation catches unknown keys, bad values and broken cross-field rules. Get
into the habit of running it after an edit; it contacts nothing and is instant.

## Look around

```bash
labops host list
```

Reads the config only, so it works offline and against machines that are
powered down.

## Make a change

```bash
labops host update nas
```

This runs the package manager appropriate to the node's `os` — apt for `debian`,
apk for `alpine`, dnf for `redhat`. To rehearse first:

```bash
labops --dry-run host update nas
```

`--dry-run` puts Ansible in check mode: it connects and reports what would
change, without changing it. `--verbose` shows the full Ansible output when
something goes wrong.

## Grow the config

Once the basics work, the config grows along whichever axis you need. Each of
these is optional and independent:

=== "Proxmox guests"

    A host with `type: proxmox` nests its guests underneath. Containers are
    reached through the Proxmox parent with `pct`, so they need no sshd of their
    own.

    ```yaml
    hosts:
      cprox:
        type: proxmox
        os: debian
        ip: 10.0.10.3
        lxc:
          pihole:
            ip: 10.0.10.5
            os: debian
            vmid: 105
        vm:
          fr24-radar:
            os: debian
            ip: 10.0.50.149
            vmid: 111
    ```

    → [hosts, vm, lxc](configuration/nodes.md)

=== "Targeted updates"

    Tag your nodes and update arbitrary slices of the lab instead of one machine
    at a time.

    ```yaml
    hosts:
      cprox:
        tags: [prod, proxmox]
    ```

    ```bash
    labops update --kind lxc --os debian   # every debian container
    labops update --under cprox            # cprox and everything below it
    labops update --all --list             # preview, run nothing
    ```

    → [Selecting targets](guides/targets.md)

=== "DNS"

    Every node becomes a record automatically; there is no record list to
    maintain.

    ```yaml
    settings:
      dns:
        local_dns_suffix: .lab
        pihole_location: pihole
    ```

    ```bash
    labops dns list   # works before you have a Pi-hole to point at
    labops dns diff
    labops dns sync
    ```

    → [Pi-hole DNS](guides/dns.md)

=== "Reverse proxy"

    Declare a service on the node that runs it, and it becomes a route.

    ```yaml
    settings:
      proxy:
        proxy_suffix: .example.com
        access_lists:
          local:
            default: true
            accept: [10.0.10.0/24]

    hosts:
      nas:
        os: unmanaged
        ip: 10.0.10.4
        web_services:
          - proxy_name: nas
            port: 80
    ```

    ```bash
    labops proxy list
    labops proxy render   # see the Caddyfile before deploying it
    ```

    → [Caddy reverse proxy](guides/proxy.md)

## Keep secrets out of the config

API tokens — your Pi-hole password, a Cloudflare token — belong in a `.env` file
next to your config, not in the config itself:

```bash
# .env, git-ignored
PIHOLE_PASSWORD=…
CF_API_TOKEN=…
```

labops only ever reads this file, never writes it. Point somewhere else with
`settings.env_file` if you keep secrets elsewhere.

## Where to next

- [Configuration reference](configuration/index.md) — every key, with defaults
- [Command reference](commands/index.md) — every command and flag
- The [guides](guides/targets.md) explain the subsystems and *why* they work the
  way they do
