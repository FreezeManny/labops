# labops

A declarative, YAML-based homelab manager.

You describe your homelab once — the machines, the containers, the services they
expose — and labops handles the rest: patching, DNS records, reverse-proxy
routes, Docker stacks. One file is the source of truth, and everything else is
derived from it.

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

That container is now three things at once: something `labops update` will patch,
a `pihole.lab` DNS record, and a `pihole.example.com` route in your Caddyfile.
Nothing was declared twice, so nothing can drift.

## What it does

<div class="grid cards" markdown>

- **Patch anything, in slices**

    Update a host, a container, or an arbitrary slice of the lab — by kind, OS,
    tag or position in the tree. [Selecting targets](guides/targets.md)

- **DNS that follows the inventory**

    Every node becomes a record, published to Pi-hole v6. Move a service, and its
    name moves with it. [Pi-hole DNS](guides/dns.md)

- **A reverse proxy you never hand-write**

    Declare a service next to the machine that runs it; labops renders the
    Caddyfile, with access lists and wildcard TLS. [Caddy proxy](guides/proxy.md)

- **Docker stacks**

    Sync compose files to a node, bring them up, pull newer images.
    [Docker stacks](guides/docker.md)

- **Wake what is asleep**

    A magic packet for bare metal, `qm` / `pct start` for a Proxmox guest —
    labops picks the one that can actually work. [Waking nodes](guides/wake.md)

- **Fail before you deploy**

    Unknown keys, bad IPs, a missing template, an illegal hostname — all caught
    by `labops validate`, not half-way through a run.

</div>

## Install

```bash
pipx install labops
```

`labops` is a standalone CLI, so [pipx](https://pipx.pypa.io/) is the natural
way to install it — `pip install labops` works too.

## Then

Point it at a config and go:

```bash
labops validate       # is the file sound?
labops host list      # what do I have?
labops update --all   # patch everything
```

[Getting started :material-arrow-right:](getting-started.md){ .md-button .md-button--primary }
[Command reference :material-arrow-right:](commands/index.md){ .md-button }

## How it works

labops is a bridge between a human-readable YAML file and Ansible.

1. **Parse.** It finds `homelab.yml` by walking up from your current directory,
   the way `docker compose` finds a compose file, and reads your layout,
   credentials and settings.
2. **Validate.** It checks structure, types and cross-field rules, so
   misconfigurations stop here rather than part-way through a change.
3. **Execute.** Depending on the command it runs internal Python routines or
   dispatches built-in Ansible playbooks at the nodes you selected — consistent
   setups and updates across Debian, Alpine and RedHat without you writing raw
   playbooks.
