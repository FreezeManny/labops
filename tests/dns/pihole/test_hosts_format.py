"""Tests for the ``dns.hosts`` text format (src/dns/pihole/client.py).

The array is free text, so this is the one place a Pi-hole record can be
*unreadable*. What matters in every case below is which side of the split a line
lands on: a record labops will publish over, or an unparsed line the plan has to
warn about before a rewrite destroys it. Silently inventing records from a line it
did not understand is the failure this module exists to prevent.
"""

from ipaddress import IPv4Address

from models.dns.record import LiveRecord
from src.dns.pihole.client import format_host_line, parse_hosts


def _names(records: list[LiveRecord]) -> list[str]:
    return [r.hostname for r in records]


# ── format ────────────────────────────────────────────────────────────────────


def test_a_line_is_ip_then_name() -> None:
    assert format_host_line(IPv4Address("10.0.0.1"), "nas.lab") == "10.0.0.1 nas.lab"


def test_formatting_round_trips_through_the_parser() -> None:
    line: str = format_host_line(IPv4Address("10.0.0.7"), "pi.lab")
    records, unparsed = parse_hosts([line])
    assert not unparsed
    assert records == [LiveRecord(hostname="pi.lab", ip=IPv4Address("10.0.0.7"))]


# ── parse ─────────────────────────────────────────────────────────────────────


def test_one_name_per_line_becomes_one_record() -> None:
    records, unparsed = parse_hosts(["10.0.0.1 nas.lab", "10.0.0.2 pi.lab"])
    assert not unparsed
    assert _names(records) == ["nas.lab", "pi.lab"]
    assert [str(r.ip) for r in records] == ["10.0.0.1", "10.0.0.2"]


def test_several_names_on_one_line_become_several_records() -> None:
    """A hosts line may alias one address; each name is its own record."""
    records, unparsed = parse_hosts(["10.0.0.1 nas nas.lab storage.lab"])
    assert not unparsed
    assert _names(records) == ["nas", "nas.lab", "storage.lab"]
    assert {str(r.ip) for r in records} == {"10.0.0.1"}


def test_surrounding_whitespace_is_not_a_record() -> None:
    records, unparsed = parse_hosts(["   10.0.0.1    nas.lab   "])
    assert not unparsed
    assert _names(records) == ["nas.lab"]


# ── comments ──────────────────────────────────────────────────────────────────


def test_a_trailing_comment_is_not_a_hostname() -> None:
    """The regression: splitting on whitespace alone made records of `#` and `my`.

    Those then read as records the config does not have, so the plan offered to
    delete them — inventing work out of a line it had misread.
    """
    records, unparsed = parse_hosts(["10.0.0.1 nas.lab  # my nas"])
    assert not unparsed
    assert _names(records) == ["nas.lab"]


def test_a_comment_with_no_space_before_it_still_ends_the_names() -> None:
    records, unparsed = parse_hosts(["10.0.0.1 nas.lab#internal"])
    assert not unparsed
    assert _names(records) == ["nas.lab"]


def test_a_whole_line_comment_is_unparsed_rather_than_dropped() -> None:
    """It carries no record, but a rewrite destroys it, so the plan must say so."""
    records, unparsed = parse_hosts(["# hand-added below", "10.0.0.1 nas.lab"])
    assert _names(records) == ["nas.lab"]
    assert unparsed == ["# hand-added below"]


# ── unreadable lines ──────────────────────────────────────────────────────────


def test_an_ipv6_record_is_unparsed_not_reinterpreted() -> None:
    records, unparsed = parse_hosts(["fd00::1 nas.lab"])
    assert records == []
    assert unparsed == ["fd00::1 nas.lab"]


def test_an_address_with_no_name_is_unparsed() -> None:
    records, unparsed = parse_hosts(["10.0.0.1"])
    assert records == []
    assert unparsed == ["10.0.0.1"]


def test_a_blank_line_is_unparsed() -> None:
    records, unparsed = parse_hosts(["", "   "])
    assert records == []
    assert unparsed == ["", "   "]


def test_a_junk_line_is_unparsed() -> None:
    records, unparsed = parse_hosts(["not an address at all"])
    assert records == []
    assert unparsed == ["not an address at all"]


def test_readable_and_unreadable_lines_are_separated_not_traded() -> None:
    """One bad line must not cost the good ones, nor hide itself among them."""
    records, unparsed = parse_hosts(
        ["10.0.0.1 nas.lab", "fd00::1 v6.lab", "10.0.0.2 pi.lab", "garbage"]
    )
    assert _names(records) == ["nas.lab", "pi.lab"]
    assert unparsed == ["fd00::1 v6.lab", "garbage"]


def test_an_empty_array_is_neither() -> None:
    assert parse_hosts([]) == ([], [])
