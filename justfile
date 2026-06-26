runner    := "uv run labops_cli.py"
system    := "debian"
test_conf := "./test-samples/homelab-test.yml"

test-args := ""
# In normal use no --file is needed — the CLI walks up from cwd and finds
# homelab.yml automatically, just like `docker compose` finds compose.yml.
# Test recipes pass --file explicitly to point at the sample config.

# ----------- DEVCONTAINER ------
container-start:
	devcontainer up --workspace-folder .
	
container-attach:
	devcontainer exec --workspace-folder . bash

pre-commit:
	uv run pre-commit run --all-files

build: pre-commit
	uv build

# Run the pytest unit-test suite (pure-logic tests; no infra access).
test:
	uv run pytest

local-install:
	pipx install --force $(ls -t dist/*.whl | head -n1) --force

install-ansible-collection:
	uv run ansible-galaxy collection install -r ansible/requirements.yml
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

lxc-list:
	{{runner}} lxc list

lxc-update system=system:
	{{runner}} lxc update {{system}}

lxc-update-all:
	{{runner}} lxc update --all

# ── Test recipes (explicit --file override) ───────────────────────────────────

test-validate:
	{{runner}} {{test-args}} --file {{test_conf}} validate

test-host-list:
	{{runner}} {{test-args}} --file {{test_conf}} host list

test-host-setup:
	{{runner}} {{test-args}} --file {{test_conf}} host setup test-system-{{system}}

test-host-update:
	{{runner}} {{test-args}} --file {{test_conf}} host update test-system-{{system}}

test-host-update-all:
	{{runner}} {{test-args}} --file {{test_conf}} host update --all

test-vm-list:
	{{runner}} {{test-args}} --file {{test_conf}} vm list

test-vm-update-all:
	{{runner}} {{test-args}} --file {{test_conf}} vm update --all

test-lxc-list:
	{{runner}} {{test-args}} --file {{test_conf}} lxc list
	
test-lxc-update:
	{{runner}} {{test-args}} --file {{test_conf}} lxc update test-system-{{system}}

test-lxc-update-all:
	{{runner}} {{test-args}} --file {{test_conf}} lxc update --all

test-docker-list:
	{{runner}} {{test-args}} --file {{test_conf}} docker stack list

test-docker-deploy stack="caddy":
	{{runner}} {{test-args}} --file {{test_conf}} docker stack --stack {{stack}} deploy

test-docker-sync stack="caddy":
	{{runner}} {{test-args}} --file {{test_conf}} docker stack --stack {{stack}} sync

test-docker-update stack="caddy":
	{{runner}} {{test-args}} --file {{test_conf}} docker stack --stack {{stack}} update

test-docker-update-all:
	{{runner}} {{test-args}} --file {{test_conf}} docker stack --all update
