"""Generate the parts of the documentation that are derived from the code.

Three artifacts, all written under docs/ and all committed:

* ``labops.schema.json`` — the config's JSON Schema. Published by the docs site,
  so a user can point their editor at it and get completion and inline
  validation while writing their own ``homelab.yml``.
* ``configuration/*.md`` — the config reference, from the same schema.
* ``commands/*.md`` — the CLI reference, from Typer.

Nothing it writes is committed — the output paths are git-ignored, and CI runs
this immediately before ``mkdocs build``. So a renamed flag or a new config
field cannot leave the documentation behind: there is no stored copy to fall out
of date. Locally, ``just docs-serve`` and ``just docs-build`` run it first for
the same reason.

It lives beside the pages it produces rather than in a ``scripts/`` directory,
and deliberately not under ``src/`` or ``models/`` — those ship in the wheel
(see ``pyproject.toml``), and a docs generator has no business in a user's
install. MkDocs copies it into the built site, which is harmless: the repository
is public anyway.

Why generate the config reference from the schema rather than render the model
classes with mkdocstrings: people write YAML here, not Python. A page shaped
like a Python class hierarchy would document a thing nobody interacts with.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS = REPO_ROOT / "docs"

sys.path.insert(0, str(REPO_ROOT))

from models.input_conf.yaml_root import YamlRoot  # noqa: E402

# ─── Config reference ─────────────────────────────────────────────────────────
#
# Which models land on which page, and the prose that introduces each one. The
# schema supplies every fact below the heading; this table supplies the framing
# the schema cannot know — what the block is for and when you would reach for it.

Page = tuple[str, str, str, list[str]]  # filename, title, intro, model names

PAGES: list[Page] = [
    (
        "index.md",
        "Configuration",
        """\
Everything labops does is driven by one file — `homelab.yml` — and this section
is the reference for it. If you are writing your first one, start with
[Getting started](../getting-started.md); if you want your editor to complete
and check these keys as you type, see [Editor setup](../editor-setup.md).

The file has exactly two top-level blocks:

```yaml
settings:   # credentials, secret store, DNS, proxy, reusable target sets
hosts:      # the inventory — every machine, with guests nested underneath
```

Unknown keys are rejected rather than ignored, everywhere in the file. A typo is
a validation error you see at `labops validate`, not a setting that silently
never applied.
""",
        ["YamlRoot"],
    ),
    (
        "settings.md",
        "settings",
        """\
Everything that is not a machine. Only `default_creds` is required — the `dns`
and `proxy` blocks are subsystems you opt into, and leaving one out simply means
the matching commands have nothing to act on and say so.
""",
        ["Settings", "Creds", "Selector"],
    ),
    (
        "nodes.md",
        "hosts, vm, lxc",
        """\
The inventory. `hosts:` holds the machines labops reaches directly; a host with
`type: proxmox` nests its guests underneath as `vm:` and `lxc:`, so the one
block describes the whole tree.

The three node kinds share most of their fields. Where they differ is *how they
are reached*: a host or VM over SSH, a container through its Proxmox parent with
`pct exec` — which is why an LXC needs no sshd, no credentials of its own and no
route from the machine running labops.

The key you write a node under is its name. That name becomes a DNS label once
`settings.dns` is configured, so it must be a legal one — no underscores —
unless `dns_name` overrides it.

Any node may be marked `os: unmanaged`. It is then tracked, resolved and proxied
like any other, but setup and update skip it: an appliance OS or a box you do
not own has no package manager for labops to drive.
""",
        ["Host", "VM", "LXC"],
    ),
    (
        "dns.md",
        "settings.dns",
        """\
Local DNS records, published to Pi-hole v6.

There is no record list. Every host, VM and LXC in the config becomes
`<name><local_dns_suffix> -> ip`, so a device that exists only to have a DNS
entry is written as an ordinary node with `os: unmanaged`. DNS therefore cannot
drift from the inventory — they are the same declaration.

See the [Pi-hole DNS guide](../guides/dns.md) for how the commands fit together.
""",
        ["Dns"],
    ),
    (
        "proxy.md",
        "settings.proxy",
        """\
The Caddy reverse proxy.

As with DNS, there is no route list: every `web_services` entry anywhere in the
tree that carries a `proxy_name` becomes a route. A service is published by
declaring it on the node that runs it, next to that node's IP.

labops owns the Caddyfile and nothing else. The Caddy image, the caddy-dns
plugin it must be built with, and the environment holding your ACME token are
managed outside labops — see the [Caddy proxy guide](../guides/proxy.md).
""",
        ["Proxy", "ProxyTls", "ProxyDeploy", "DockerDeploy", "AccessList"],
    ),
    (
        "web-services.md",
        "web_services",
        """\
An HTTP service exposed by a node or by a Docker stack. This is the whole of
how routes get into the proxy.

An entry without a `proxy_name` is tracked but not routed — useful for recording
what a port is without publishing it.
""",
        ["WebService"],
    ),
    (
        "docker.md",
        "docker",
        """\
Docker Compose stacks running on a node. labops owns getting the stack's
directory onto the node and running compose there; what is inside the compose
file is yours.

See the [Docker stacks guide](../guides/docker.md).
""",
        ["Docker", "StackEntry"],
    ),
]

# Which page each model is documented on, so cross-references can link to it.
MODEL_PAGE: dict[str, str] = {
    model: filename for filename, _, _, models in PAGES for model in models
}
# WebServices is the list wrapper around WebService; link through to the item.
MODEL_PAGE["WebServices"] = MODEL_PAGE["WebService"]


def anchor(model: str) -> str:
    return model.lower()


def link_to(model: str, current_page: str) -> str:
    """A markdown link to ``model``'s section, relative to ``current_page``."""
    target = MODEL_PAGE.get(model)
    if target is None:
        return f"`{model}`"
    label = "WebService" if model == "WebServices" else model
    if target == current_page:
        return f"[{label}](#{anchor(label)})"
    return f"[{label}]({target}#{anchor(label)})"


FORMAT_NAMES = {
    "ipv4": "IPv4 address",
    "ipvanynetwork": "CIDR",
    "file-path": "path to a file",
    "directory-path": "path to a directory",
}

# Populated once per run, so $refs can be resolved while rendering a type.
DEFS: dict[str, Any] = {}


def type_name(spec: dict[str, Any], page: str) -> str:
    """Render a JSON-Schema type as something a YAML author recognises."""
    if "$ref" in spec:
        target = spec["$ref"].rsplit("/", 1)[-1]
        definition = DEFS.get(target, {})
        # A RootModel (WebServices wraps a list of WebService) has no properties
        # of its own and nothing to link to — render what it actually is.
        if "properties" not in definition and definition.get("type") == "array":
            return type_name(definition, page)
        return link_to(target, page)

    if "anyOf" in spec:
        # Optional[X] is anyOf[X, null]; the null is carried by the Required
        # column instead, so drop it rather than printing "or null".
        variants = [v for v in spec["anyOf"] if v.get("type") != "null"]
        return " or ".join(type_name(v, page) for v in variants)

    if "enum" in spec:
        return " \\| ".join(f"`{v}`" for v in spec["enum"])

    kind = spec.get("type")

    if kind == "array":
        return f"list of {type_name(spec.get('items', {}), page)}"

    if kind == "object":
        extra = spec.get("additionalProperties")
        if isinstance(extra, dict):
            return f"map of name → {type_name(extra, page)}"
        return "map"

    if kind == "string":
        fmt = spec.get("format")
        if fmt in FORMAT_NAMES:
            return FORMAT_NAMES[fmt]
        return "string"

    if kind == "integer":
        return "integer"
    if kind == "boolean":
        return "boolean"

    return kind or "any"


def default_cell(spec: dict[str, Any], required: bool) -> str:
    if required:
        return "**required**"
    if "default" not in spec:
        return "—"
    value = spec["default"]
    if value is None:
        return "*unset*"
    if value == [] or value == {}:
        return "*empty*"
    return f"`{json.dumps(value)}`"


def clean_description(text: str) -> str:
    """Collapse a field description onto one line, for a table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def model_section(name: str, definition: dict[str, Any], page: str) -> str:
    """One model: its docstring, then a table of its keys."""
    out: list[str] = [f"## {name}", ""]

    doc = definition.get("description")
    if doc:
        # Pydantic hands us the class docstring verbatim. Its paragraphs are
        # already prose; keep them, and let RST-style ``literals`` pass through
        # as markdown code spans, which they happen to be.
        out += [doc.strip(), ""]

    properties: dict[str, Any] = definition.get("properties") or {}
    if not properties:
        return "\n".join(out)

    required: set[str] = set(definition.get("required") or [])

    out += ["| Key | Type | Default | Description |", "| --- | --- | --- | --- |"]
    for key, spec in properties.items():
        # Fields labops fills in itself (a node's name comes from its YAML key)
        # are documented in place rather than hidden: someone will try to set
        # one, and the table is where they look.
        out.append(
            f"| `{key}` "
            f"| {type_name(spec, page)} "
            f"| {default_cell(spec, key in required)} "
            f"| {clean_description(spec.get('description', ''))} |"
        )
    out.append("")
    return "\n".join(out)


def write_config_reference(schema: dict[str, Any]) -> list[Path]:
    defs: dict[str, Any] = dict(schema.get("$defs") or {})
    # The root model has no $defs entry of its own; give it one so the page
    # table below can treat every model the same way.
    defs["YamlRoot"] = {
        k: v for k, v in schema.items() if k not in {"$defs", "$schema"}
    }
    DEFS.clear()
    DEFS.update(defs)

    target_dir = DOCS / "configuration"
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for filename, title, intro, models in PAGES:
        body = [
            "<!-- Generated by scripts/gen_docs.py — do not edit by hand. -->",
            "",
            f"# {title}",
            "",
            intro.strip(),
            "",
        ]
        for model in models:
            body.append(model_section(model, defs[model], filename))

        path = target_dir / filename
        path.write_text("\n".join(body).rstrip() + "\n")
        written.append(path)

    return written


# ─── Command reference ────────────────────────────────────────────────────────
#
# `typer ... utils docs` gives us the whole command tree, but it renders the
# app's rich markup ([bold], [dim]) as inline HTML spans with literal colours,
# and HTML-escapes the prose. Both have to be undone before the result is
# usable as markdown — the alternative, turning off rich_markup_mode, would fix
# the docs by degrading `--help` in the terminal.

BOLD_SPAN = re.compile(
    r'<span style="[^"]*font-weight: bold[^"]*">(.*?)</span>', re.DOTALL
)
ANY_SPAN = re.compile(r"<span style=\"[^\"]*\">(.*?)</span>", re.DOTALL)


def strip_rich_markup(text: str) -> str:
    text = BOLD_SPAN.sub(r"**\1**", text)
    # Everything else rich emitted — [dim] and colour tags — carries emphasis we
    # cannot express in a table-of-contents-friendly way, so it becomes plain
    # prose rather than a nest of italics.
    text = ANY_SPAN.sub(r"\1", text)
    return html.unescape(text)


def fence_example_blocks(text: str) -> str:
    """Turn Typer's ``\\b`` example blocks into fenced code.

    Click emits them as an ``Examples:`` line followed by two-space-indented
    lines. Two spaces is not enough for a markdown code block, so the alignment
    that makes the examples readable would be reflowed away.
    """
    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        is_examples = line.strip() == "Examples:"
        # Match the "**Usage**:" / "**Options**:" headings Typer emits, so the
        # examples read as a section rather than a stray sentence.
        out.append("**Examples**:" if is_examples else line)
        if is_examples:
            block: list[str] = []
            j = i + 1
            while j < len(lines) and (lines[j].startswith("  ") or not lines[j].strip()):
                if not lines[j].strip() and not any(
                    lines[k].startswith("  ") for k in range(j + 1, min(j + 3, len(lines)))
                ):
                    break
                block.append(lines[j][2:] if lines[j].startswith("  ") else "")
                j += 1
            while block and not block[-1].strip():
                block.pop()
            if block:
                out += ["", "```console", *block, "```"]
                i = j
                continue
        i += 1
    return "\n".join(out)


def demote_headings(text: str) -> str:
    """Shift every heading up one level, so a section can start its own page."""
    return re.sub(r"^(#{2,})( )", lambda m: m.group(1)[1:] + " ", text, flags=re.M)


# Command group -> page filename. Groups not listed here are folded into the
# index, which keeps single-command pages from proliferating.
COMMAND_PAGES: dict[str, str] = {
    "update": "update.md",
    "wake": "wake.md",
    "validate": "validate.md",
    "host": "host.md",
    "vm": "vm.md",
    "lxc": "lxc.md",
    "docker": "docker.md",
    "proxy": "proxy.md",
    "dns": "dns.md",
}


def write_command_reference() -> list[Path]:
    raw = subprocess.run(
        [sys.executable, "-m", "typer", "labops_cli.py", "utils", "docs", "--name", "labops"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    text = fence_example_blocks(strip_rich_markup(raw))

    # Split on the top-level command headings; everything before the first one
    # is the root app: global options and the command list.
    parts = re.split(r"^## `labops ([a-z-]+)`", text, flags=re.M)
    root = parts[0]
    sections = list(zip(parts[1::2], parts[2::2]))

    target_dir = DOCS / "commands"
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    banner = "<!-- Generated by scripts/gen_docs.py — do not edit by hand. -->\n"

    index = [
        banner,
        root.strip(),
        "",
        "Each command group has its own page:",
        "",
    ]
    index += [f"* [`labops {name}`]({COMMAND_PAGES[name]})" for name, _ in sections]

    (target_dir / "index.md").write_text("\n".join(index).rstrip() + "\n")
    written.append(target_dir / "index.md")

    for name, body in sections:
        page = [banner, f"# `labops {name}`", "", demote_headings(body).strip()]
        path = target_dir / COMMAND_PAGES[name]
        path.write_text("\n".join(page).rstrip() + "\n")
        written.append(path)

    return written


def main() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)

    schema = YamlRoot.model_json_schema()
    schema_path = DOCS / "labops.schema.json"
    schema_path.write_text(json.dumps(schema, indent=2) + "\n")

    written: list[Path] = [schema_path]
    written += write_config_reference(schema)
    written += write_command_reference()

    for path in written:
        print(f"  wrote {path.relative_to(REPO_ROOT)}")
    print(f"{len(written)} files generated.")


if __name__ == "__main__":
    main()
