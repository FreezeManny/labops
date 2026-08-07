![#Labops - A declarative, YAML-based homelab manager](img/Cover.png)

A declarative, YAML-based homelab manager. `labops` is a CLI tool designed to simplify, automate, and standardize the setup, configuration, and maintenance of your homelab infrastructure utilizing simple configuration files and powerful backend automation.

## Features

### Current Capabilities
- **Declarative YAML Configuration**: Define your complete homelab environment comprehensively using simple YAML configuration files.
- **Host Management**: Automated setup, initialization, and system updates for a variety of host operating systems (Alpine, Debian, RedHat) powered by integrated Ansible playbooks.
- **Proxmox LXC**: Update Proxmox Linux Containers (LXC) natively (through Proxmox Root Host)
- **Target Selection**: Update an arbitrary slice of the homelab — by node kind, OS, tag, or position in the tree — either ad-hoc or from a reusable named set in your config.

### Roadmap & Future Scope
- **Docker Stack Management**: Seamlessly deploy, spin up, and manage Docker Compose stacks across your nodes.
- **DNS Automation**: Automated updating of internal DNS records.
- **Reverse Proxy Orchestration**: Manage, update, and automate reverse proxy routes

## How it Works

`labops` acts as a bridge between simple, human-readable YAML configurations and powerful Ansible Commands. 

1. **Configuration parsing:** It reads a declarative `.yml` inventory representing your homelab layout, target servers, credentials, and settings.
2. **Validation:** It validates the YAML structure and data format to stop misconfigurations early.
3. **Execution:** Based on the commands executed, it triggers internal Python routines or dispatches built-in Ansible playbooks targeting the defined hosts. This ensures consistent host setups, OS updates (Debian, RedHat, Alpine), and more without writing raw playbook files manually.

## Installation

You can install `labops` easily via pip:

```bash
pipx install labops
#or
pip install labops
```
*Since `labops` is a standalone CLI tool, using [pipx](https://pipx.pypa.io/) is highly recommended to isolate its dependencies*

## Usage

Once installed, the `labops` command becomes available. Point it to your YAML configuration file (e.g., `test-samples/homelab-complete.yml`):

```bash
# View all available CLI commands
labops --help

# Example: Update every host
labops host update --all
```

### Custom updates

`labops update` acts on a *selection* rather than a single target. A selection is
four optional filters — kind, OS, tag and position in the tree — combined as **AND
across filters and OR within one**, and it covers both the matching nodes and the
Docker stacks running on them.

```bash
labops update --kind lxc --os debian     # every Debian container
labops update --under cprox              # cprox and everything below it
labops update --tag prod --only stacks   # only the stacks on prod-tagged nodes
labops update --all --list               # preview everything, run nothing
```

`--list` prints the resolved targets and exits, and every run shows that same
preview before it asks to proceed (`--yes` skips the prompt, `--dry-run` runs
Ansible in check mode).

Tag your nodes to make them selectable. Tags are local — a container is only
`prod` if it says so itself, so use `--under` to sweep a whole subtree:

```yaml
hosts:
  cprox:
    tags: [prod, proxmox]
```

Selections you run often belong in the config as named target sets, invoked by
name (`labops update weekly`):

```yaml
settings:
  targets:
    weekly:
      kind: [vm, lxc]
      os: [debian]
```

## Development & Building

This project utilizes [Dev Containers](https://containers.dev/) to provide a seamless, consistent development environment, and uses [uv](https://github.com/astral-sh/uv) for lightning-fast Python package management.

### 1. Development Environment

To start developing locally without installing system-level dependencies:

1. Open the project in VS Code (or any editor supporting Dev Containers).
2. When prompted, click **Reopen in Container** (this builds your development environment with Python, Ansible, and other necessary CLI tools pre-installed).
3. Once the container is running and your terminal is open, sync the dependencies and activate the virtual environment:

```bash
# Create the virtual environment and install dependencies + the labops CLI
uv sync

# Activate the virtual environment
source .venv/bin/activate

# Now you can run the CLI
labops --help
```

### 2. Building the Package
The package does not have to be manually updated to PyPi, as it utalizes github actions to build and publish it.

To build the standard Python distribution files locally (Wheel `.whl` and Source Distribution `.tar.gz`) for testing:

```bash
uv build
```

This will generate the artifacts inside the `dist/` directory.
