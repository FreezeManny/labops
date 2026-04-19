runner    := "uv run labops_cli.py"
system    := "redhat"
test_conf := "./test-samples/homelab-complete.yml"

# In normal use no --file is needed — the CLI walks up from cwd and finds
# homelab.yml automatically, just like `docker compose` finds compose.yml.
# Test recipes pass --file explicitly to point at the sample config.

pre-commit:
	uv run pre-commit run --all-files

# ── Normal usage (auto-discovers homelab.yml from cwd) ────────────────────────

validate:
	{{runner}} validate

host-list:
	{{runner}} host list

host-setup system=system:
	{{runner}} host setup {{system}}

host-update system=system:
	{{runner}} host update {{system}}

host-update-all:
	{{runner}} host update --all

vm-list:
	{{runner}} vm list

vm-update system=system:
	{{runner}} vm update {{system}}

vm-update-all:
	{{runner}} vm update --all

# ── Test recipes (explicit --file override) ───────────────────────────────────

test-validate:
	{{runner}} --file {{test_conf}} validate

test-host-list:
	{{runner}} --file {{test_conf}} host list

test-host-setup:
	{{runner}} --file {{test_conf}} host setup test-system-{{system}}

test-host-update:
	{{runner}} --file {{test_conf}} host update test-system-{{system}}

test-host-update-all:
	{{runner}} --file {{test_conf}} host update --all

test-vm-list:
	{{runner}} --file {{test_conf}} vm list

test-vm-update-all:
	{{runner}} --file {{test_conf}} vm update --all