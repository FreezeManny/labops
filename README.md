# Homelab Manager (lops)

YAML Based homelab Manager

## Development & Testing Locally

This project uses [uv](https://github.com/astral-sh/uv) for fast Python package and environment management.

### 1. Setup and Install Locally

To test the CLI locally, install the dependencies and the project itself into a virtual environment using `uv sync`:

```bash
# Create the virtual environment and install dependencies + the lops CLI
uv sync

# Activate the virtual environment
source .venv/bin/activate

# Now you can run the CLI
lops --help
```

### 2. Building the Package

To build the standard Python distribution files (Wheel `.whl` and Source Distribution `.tar.gz`) for publishing or CI/CD pipelines (such as GitHub Actions):

```bash
uv build
```

This will generate the artifacts inside the `dist/` directory.
