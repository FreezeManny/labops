# Waking nodes

```bash
labops wake nas
```

One verb, two mechanisms — and labops picks the one that can actually work.

## Why there are two

**A bare-metal host** answers a Wake-on-LAN magic packet sent to the `mac` in its
config.

**A Proxmox guest does not.** Nothing inside a stopped VM or container is
listening for a packet, and Proxmox does not watch for one on a guest's behalf.
A guest is started by its parent instead, with `qm start` or `pct start`.

Choosing automatically is the point: `labops wake nas` does the right thing
whether `nas` is a box on a shelf or a VM. The rule is one line — a guest is
started unless you explicitly asked for a packet — and the command always prints
which path it took, so you never have to infer it from the outcome.

## Bare metal

Give the node the MAC of the NIC that listens:

```yaml
hosts:
  nas:
    os: unmanaged
    ip: 10.0.10.4
    mac: bc:24:11:aa:bb:cc
```

Colon, dash (`BC-24-11-AA-BB-CC`) and dotted (`bc24.11aa.bbcc`) notation are all
accepted and normalised.

!!! warning "Magic packets do not cross subnets"
    A magic packet goes to the **broadcast** address — the machine is off, so its
    IP resolves to nothing — and routers do not forward broadcast traffic.

    Either run labops on the same segment, or relay it from a node that is:

    ```bash
    labops wake nas --via cprox
    ```

## Proxmox guests

Nothing to configure. labops finds the guest's parent and its `vmid`, and starts
it there:

```bash
labops wake fr24-radar    # qm start 111 on cprox
labops wake pihole        # pct start 105 on cprox
```

A guest needs no `mac` for this. Set one only if the guest has a NIC of its own
that really does wake, and then ask for the packet explicitly:

```bash
labops wake fr24-radar --packet
```

## Waiting for it

Powering on returns immediately; the machine takes a while to be useful. `--wait`
polls until it answers:

```bash
labops wake nas --wait 120              # up to 120s, polling TCP :22
labops wake nas --wait 120 --wait-port 443
```

## What can be woken

```bash
labops wake --list
```

Lists every node with a `mac`, so you can see what is reachable this way before
you need it.

## See also

- [`labops wake` reference](../commands/wake.md) — every flag
- [Node configuration](../configuration/nodes.md) — where `mac` lives
