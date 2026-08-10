"""Building and sending a Wake-on-LAN magic packet.

The packet is trivial — six ``0xff`` bytes followed by the target MAC repeated
sixteen times — and it goes out as a UDP broadcast, so this is stdlib sockets
rather than a dependency. It is deliberately separate from the Ansible relay in
``run.py``: sending from the machine running labops needs no remote host at all,
and it is the common case (laptop and NAS on the same wire).

Broadcast, not unicast: the target is powered off, so nothing answers ARP and its
IP resolves to nothing. ``255.255.255.255`` is the limited broadcast — it reaches
the local segment and is not forwarded, which is why ``--via`` exists for the case
where labops runs somewhere else.
"""

import socket

# The IANA "discard" port. Port 7 (echo) is the other convention; WoL NICs listen
# below the IP stack and take either, so one default plus --port covers it.
DEFAULT_PORT = 9
DEFAULT_BROADCAST = "255.255.255.255"


def magic_packet(mac: str) -> bytes:
    """The 102-byte magic packet for ``mac``.

    ``mac`` comes from the config, where ``pydantic_extra_types``' ``MacAddress``
    has already validated it and normalised it to ``aa:bb:cc:dd:ee:ff`` — so the
    separators are all this has to strip.
    """
    return b"\xff" * 6 + bytes.fromhex(mac.replace(":", "")) * 16


def send_magic_packet(
    mac: str, broadcast: str = DEFAULT_BROADCAST, port: int = DEFAULT_PORT
) -> None:
    """Broadcast the magic packet for ``mac`` from this machine.

    Raises ValueError with a plain sentence when the socket refuses — an
    unroutable broadcast address is a user mistake (wrong subnet, no link), not
    something to hand back as a traceback.
    """
    packet: bytes = magic_packet(mac)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, (broadcast, port))
    except OSError as e:
        raise ValueError(
            f"could not send the magic packet to {broadcast}:{port} ({e}). "
            "Check the broadcast address is right for this machine's network, or "
            "relay it from a node on the target's segment with --via."
        ) from e
