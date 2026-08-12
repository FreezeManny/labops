![#Labops - A declarative, YAML-based homelab manager](img/Cover.png)

A declarative, YAML-based homelab manager. `labops` is a CLI tool that simplifies, automates and standardizes the setup, configuration and maintenance of your homelab infrastructure using simple configuration files and powerful backend automation.

**📖 [Documentation](https://freezemanny.github.io/labops/)** &nbsp;·&nbsp; [Getting started](https://freezemanny.github.io/labops/getting-started/) &nbsp;·&nbsp; [Configuration](https://freezemanny.github.io/labops/configuration/) &nbsp;·&nbsp; [Commands](https://freezemanny.github.io/labops/commands/)

## What it does

You describe your homelab once — the machines, the containers, the services they expose — and labops derives the rest from it.

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
        web_services:
          - proxy_name: pihole
            port: 8080
```

That container is now three things at once: something `labops update` will patch, a `pihole.lab` DNS record, and a `pihole.example.com` route in your Caddyfile. Nothing was declared twice, so nothing can drift.

- **Host management** — setup and updates across Alpine, Debian and RedHat, via built-in Ansible playbooks
- **Proxmox VMs & LXC** — containers driven through the Proxmox host with `pct`, so they need no sshd
- **Target selection** — update an arbitrary slice of the lab by kind, OS, tag or position in the tree, ad-hoc or from a named set
- **Docker stacks** — sync compose files to a node, bring them up, pull newer images
- **DNS automation** — every node becomes a Pi-hole v6 record, derived from the inventory
- **Reverse proxy** — a Caddyfile rendered from your `web_services`, with access lists and wildcard TLS
- **Wake** — a magic packet for bare metal, `qm` / `pct start` for a Proxmox guest

## Installation

```bash
pipx install labops
# or
pip install labops
```

*Since `labops` is a standalone CLI tool, using [pipx](https://pipx.pypa.io/) is highly recommended to isolate its dependencies.*

## Usage

Point it at a YAML config and go. `labops` finds `homelab.yml` by walking up from your current directory, the way `docker compose` finds a compose file.

```bash
labops --help          # every available command
labops validate        # is the config sound?
labops host list       # what do I have?
labops update --all    # patch everything
```

A worked example config lives in [`test-samples/homelab-complete.yml`](test-samples/homelab-complete.yml).

→ **[Full documentation](https://freezemanny.github.io/labops/)**, including a [configuration reference](https://freezemanny.github.io/labops/configuration/) and a [JSON Schema](https://freezemanny.github.io/labops/configuration/editor-setup/) for editor autocompletion.

## Development

See the [development guide](https://freezemanny.github.io/labops/development/) for the full setup. In short:

```bash
uv sync
source .venv/bin/activate

just check      # lint + type-check
just test       # pytest
just docs-serve # preview the docs site
```

The project uses [Dev Containers](https://containers.dev/) for a consistent environment and [uv](https://github.com/astral-sh/uv) for package management. Releases are automated with release-please; the package is published to PyPI by GitHub Actions, not by hand.
