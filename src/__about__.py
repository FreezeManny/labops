# The single source of truth for the version, deliberately kept out of
# pyproject.toml. uv records a version for the root package in uv.lock only when
# pyproject states one statically, so a release bump there left the lock stale
# and `uv sync --locked` failed on every release PR. With a dynamic version the
# lock carries no version at all and the bump cannot desynchronise it.
__version__ = "0.11.1"  # x-release-please-version
