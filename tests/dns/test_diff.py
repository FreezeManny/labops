"""Tests for src/dns/diff.py — what a sync would change on one Pi-hole.

The diff drives a destructive write, so the distinction that matters most here is
update-vs-delete: an address change must not read as a deletion, because deletions
are what trigger the confirmation prompt.
"""

from ipaddress import IPv4Address

from models.dns.record import DnsPlan, DnsRecord, LiveRecord
from src.dns import diff_records


def _desired(*pairs: tuple[str, str]) -> list[DnsRecord]:
    return [
        DnsRecord(hostname=host, ip=IPv4Address(ip), path=[host]) for host, ip in pairs
    ]


def _live(*pairs: tuple[str, str]) -> list[LiveRecord]:
    return [LiveRecord(hostname=host, ip=IPv4Address(ip)) for host, ip in pairs]


def test_missing_record_is_an_addition() -> None:
    plan: DnsPlan = diff_records(_desired(("nas.lab", "10.0.0.5")), [])
    assert [r.hostname for r in plan.add] == ["nas.lab"]
    assert not plan.update and not plan.remove and not plan.unchanged


def test_identical_record_is_unchanged() -> None:
    plan = diff_records(
        _desired(("nas.lab", "10.0.0.5")), _live(("nas.lab", "10.0.0.5"))
    )
    assert [r.hostname for r in plan.unchanged] == ["nas.lab"]
    assert not plan.has_changes


def test_changed_address_is_an_update_not_a_delete() -> None:
    plan = diff_records(
        _desired(("nas.lab", "10.0.0.9")), _live(("nas.lab", "10.0.0.5"))
    )
    assert not plan.remove
    assert not plan.add
    assert len(plan.update) == 1
    assert plan.update[0].record.ip == IPv4Address("10.0.0.9")
    assert plan.update[0].current_ips == [IPv4Address("10.0.0.5")]
    assert plan.has_changes
    assert not plan.has_deletions


def test_unknown_record_is_removed() -> None:
    plan = diff_records(
        _desired(("nas.lab", "10.0.0.5")),
        _live(("nas.lab", "10.0.0.5"), ("deskswitch.lab", "10.0.0.14")),
    )
    assert [r.hostname for r in plan.remove] == ["deskswitch.lab"]
    assert plan.has_deletions


def test_hostname_published_twice_is_a_single_update() -> None:
    # Pi-hole's dns.hosts is an array, so one hostname may appear twice. Writing
    # the config collapses it to the one desired address — one update, not a
    # delete plus an add.
    plan = diff_records(
        _desired(("nas.lab", "10.0.0.5")),
        _live(("nas.lab", "10.0.0.5"), ("nas.lab", "10.0.0.6")),
    )
    assert len(plan.update) == 1
    assert plan.update[0].current_ips == [IPv4Address("10.0.0.5"), IPv4Address("10.0.0.6")]
    assert not plan.remove
    assert not plan.unchanged


def test_aliases_pointing_at_one_address() -> None:
    plan = diff_records(
        _desired(("hass.lab", "10.0.0.20"), ("ha.lab", "10.0.0.20")),
        _live(("hass.lab", "10.0.0.20")),
    )
    assert [r.hostname for r in plan.add] == ["ha.lab"]
    assert [r.hostname for r in plan.unchanged] == ["hass.lab"]


def test_empty_config_removes_everything() -> None:
    # Full authority, stated plainly: no records in the config means no records on
    # the Pi-hole.
    plan = diff_records([], _live(("a.lab", "10.0.0.1"), ("b.lab", "10.0.0.2")))
    assert len(plan.remove) == 2
    assert plan.has_deletions


def test_unparsed_lines_land_on_the_plan_as_deletions() -> None:
    # They are not records, but the write destroys them, so they must make the plan
    # both "changed" and "destructive" — otherwise a sync drops them with no prompt.
    plan = diff_records(
        _desired(("nas.lab", "10.0.0.5")),
        _live(("nas.lab", "10.0.0.5")),
        ["fe80::1 v6.lab"],
    )
    assert plan.unparsed == ["fe80::1 v6.lab"]
    assert not plan.remove
    assert plan.has_changes
    assert plan.has_deletions


def test_no_unparsed_lines_means_no_changes() -> None:
    plan = diff_records(
        _desired(("nas.lab", "10.0.0.5")), _live(("nas.lab", "10.0.0.5"))
    )
    assert plan.unparsed == []
    assert not plan.has_changes
    assert not plan.has_deletions
