# Docker stacks

A stack is a directory of Compose files on your machine, plus the node that
should run it. labops owns getting that directory onto the node and running
`docker compose` there. What is inside the Compose file is yours.

## Declaring a stack

```yaml
hosts:
  cprox:
    hypervisor: proxmox
    os: debian
    ip: 10.0.10.3
    lxc:
      home:
        ip: 10.0.10.10
        os: debian
        vmid: 103
        docker:
          root_path: /home/manuel
          stacks:
            homeassistant:
              config_path: ./docker/homeassistant/
              web_services:
                - proxy_name: home
                  port: 8123
                - proxy_name: esphome
                  port: 6052
```

- `config_path` is a **local** directory, relative to your config file. It must
  exist, so a typo fails at `labops validate` rather than part-way through a
  deploy.
- `root_path` is the directory on the node that stacks are copied into; each
  lands in a subdirectory named after it. It must be absolute: it is resolved on
  the node, so a relative value would land wherever SSH logged in.
- `web_services` here work exactly as they do on a node — the resulting route
  points at whichever node runs the stack. See [Caddy reverse proxy](proxy.md).

## The three verbs

They differ only in how far they go:

| Command | Copies files | Runs compose |
| --- | --- | --- |
| `sync` | ✅ | ❌ |
| `deploy` | ✅ | ✅ `up -d` |
| `update` | ❌ | ✅ pull + recreate changed |

```bash
labops docker stack list --all
labops docker stack deploy homeassistant
labops docker stack update --all
labops docker stack sync caddy
```

**`update` takes many stacks at once; `deploy` and `sync` take one.** Patching
everything is a routine sweep, so `update` accepts `--all` and `--node`. Pushing
files to a node is not something to do in bulk by accident, so the other two
require a single unambiguous target.

Use `sync` when you have edited a Compose file but do not want to restart
anything yet; `deploy` when you want the change live; `update` when the Compose
file has not changed and you just want newer images.

## Targeting

```bash
labops docker stack update --all            # every stack, everywhere
labops docker stack update --node home      # every stack on one node
labops docker stack deploy homeassistant    # one stack, by name
```

Stack names need not be unique across the config. A name that matches several
nodes is an **error** asking for `--node`, not a guess:

```
Error: Stack 'nginx' exists on multiple nodes: cprox/docker, cprox/home.
Use --node to specify which one.
```

`--node` matches any name in the path — a host, a VM or a container.

## Or just sweep everything

`labops update` covers the stacks running on the nodes it matches, so a routine
patch run does not need these commands at all:

```bash
labops update --all                      # nodes and their stacks
labops update --tag prod --only stacks   # only the stacks on prod-tagged nodes
```

See [Selecting targets](targets.md).

## See also

- [`docker` configuration reference](../configuration/docker.md)
- [`labops docker` reference](../commands/docker.md)
