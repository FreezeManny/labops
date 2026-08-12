# Caddy reverse proxy

labops renders a Caddyfile from your config and delivers it. As with DNS, there
is no route list to maintain — routes are derived from the services you declare
on your machines.

```
homelab.yml  ──►  Caddyfile.j2  ──►  Caddyfile  ──►  target  ──►  caddy reload
  web_services +                       render        sync         deploy / reload
  settings.proxy
```

## Declaring a service

A `web_services` entry on the node that runs the service:

```yaml
settings:
  proxy:
    proxy_suffix: .example.com
    access_lists:
      local:
        default: true
        accept:
          - 10.0.10.0/24

hosts:
  nas:
    type: bare-metal
    os: unmanaged
    ip: 10.0.10.4
    web_services:
      - proxy_name: nas         # -> nas.example.com  ->  10.0.10.4:80
        port: 80
```

Any entry with a `proxy_name` becomes a route. One without is tracked but not
routed — useful for recording what a port is without publishing it.

Stacks can declare services too, and the route points at whichever node runs the
stack:

```yaml
    docker:
      root_path: /home/manuel
      stacks:
        homeassistant:
          config_path: ./docker/homeassistant/
          web_services:
            - proxy_name: home
              port: 8123
```

Declaring a service next to the thing that serves it is the point: move the
stack to another node and its route follows, because the route was never written
down separately.

## Access lists

Named CIDR sets, referenced by name, so "who may reach this" is declared once:

```yaml
settings:
  proxy:
    access_lists:
      local:
        default: true          # used by services with no explicit access
        accept:
          - 10.0.10.0/24
          - 10.0.20.0/24
        deny:
          - 10.0.10.66/32      # deny wins over accept
      vpn:
        accept:
          - 100.64.0.0/10      # tailscale
      open:
        accept:
          - 0.0.0.0/0
          - ::/0
```

Then per service:

```yaml
      - proxy_name: nas
        port: 80
        access: [open]          # accept-all -> public
      - proxy_name: sync
        port: 20910
        access: [local, vpn]    # the union of both lists
      - proxy_name: pve
        port: 8006
        access: vpn             # a single list may be written bare
        https: true             # upstream speaks HTTPS with a self-signed cert
```

Exactly one list must be marked `default: true` — a service with no explicit
`access` has to resolve to something.

!!! danger "An IPv4-only accept list denies IPv6 clients"
    `0.0.0.0/0` does not match an IPv6 client, so a service you meant to be
    public returns 403 over IPv6. A truly open list needs `::/0` alongside it.

## TLS

With a `tls:` block, labops issues a wildcard certificate for your suffix via the
provider's ACME DNS-01 challenge:

```yaml
settings:
  proxy:
    tls:
      provider: cloudflare     # none | cloudflare
```

No token appears here. labops renders `dns cloudflare {env.CF_API_TOKEN}` and
Caddy resolves that variable from its own environment at run time, so the secret
never lands in your config or in the rendered Caddyfile. labops reads the same
key from your `.env` only so it can warn when it is missing.

Omit the whole `tls:` block to serve the wildcard over plain HTTP — sensible for
an internal suffix with no certificate.

!!! important "labops owns the Caddyfile, not Caddy"
    The Caddy image, the `caddy-dns` plugin your provider needs, and the
    environment holding the token are managed outside labops. labops cannot
    check that your image was built with the right plugin, so the generated
    Caddyfile records which one is required as a comment.

    This is also why token problems surface as **warnings** rather than errors:
    labops can see your config and your `.env`, but not the container's own
    environment — where the token may perfectly well live.

## Delivering it

```bash
labops proxy list      # the routes, with resolved access lists  (no network)
labops proxy render    # print the Caddyfile                      (no network)
labops proxy sync      # copy it to the target                    (no reload)
labops proxy reload    # reload Caddy against what is on disk     (no sync)
labops proxy deploy    # sync + reload, and only reload if changed
```

`deploy` is the everyday command. Because it skips the reload when the file on
the target is already identical, it is safe to run repeatedly.

`render` is how you check a change before it goes anywhere:

```bash
labops proxy render
labops proxy render -o ./Caddyfile   # save a copy
```

!!! warning "There is no `caddy validate` step"
    A Caddyfile that renders successfully but that Caddy rejects will land on the
    target and fail at reload. Check with `proxy render` first.

## Where Caddy runs

`sync`, `deploy` and `reload` need to know. Omit the `deploy:` block entirely for
render-only use.

=== "Docker"

    The presence of a `docker:` block selects docker mode.

    ```yaml
    settings:
      proxy:
        deploy:
          target: docker                 # a node in this config
          caddyfile_dest: /home/manuel/Caddy/volumes/caddy/Caddyfile
          docker:
            container: caddy             # container to docker exec into
            # container_caddyfile_path: /etc/caddy/Caddyfile   # default
    ```

    `caddyfile_dest` is the path on the *host*, which is bind-mounted into the
    container at `container_caddyfile_path`.

=== "Host"

    A bare `caddy` on the target. Omit the `docker:` block; target and
    destination are all you need.

    ```yaml
    settings:
      proxy:
        deploy:
          target: lifeboat
          caddyfile_dest: /etc/caddy/Caddyfile
    ```

=== "Custom reload"

    Replace the reload command outright; it runs verbatim over SSH.

    ```yaml
          reload_command: >-
            docker compose -f /home/manuel/Caddy/compose.yml exec caddy
            caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
    ```

The `target` is any host, VM or LXC in your config, by name, IP or vmid. Hosts
and VMs are reached over SSH; an LXC is reached through its Proxmox parent with
`pct`, so the container needs no sshd.

`caddyfile_dest` must be absolute — it is resolved on the target, where a
relative path would land in the remote login directory.

## See also

- [Caddyfile templates](proxy-templates.md) — rendering from your own Jinja template
- [`settings.proxy` reference](../configuration/proxy.md)
- [`web_services` reference](../configuration/web-services.md)
- [`labops proxy` reference](../commands/proxy.md)
