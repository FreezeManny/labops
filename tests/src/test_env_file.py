"""Tests for src/utils/env_file.py — locating and parsing the .env secret store."""

from pathlib import Path

from src.utils.env_file import resolve_env_file, read_env_file


def test_resolve_defaults_to_dotenv_next_to_config() -> None:
    cfg = Path("/home/me/infra/homelab.yml")
    assert resolve_env_file(cfg, None) == Path("/home/me/infra/.env")


def test_resolve_relative_override_is_anchored_to_config_dir() -> None:
    cfg = Path("/home/me/infra/homelab.yml")
    assert resolve_env_file(cfg, "secrets/prod.env") == Path(
        "/home/me/infra/secrets/prod.env"
    )


def test_resolve_absolute_override_is_used_verbatim() -> None:
    cfg = Path("/home/me/infra/homelab.yml")
    assert resolve_env_file(cfg, "/etc/labops/prod.env") == Path("/etc/labops/prod.env")


def test_read_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_env_file(tmp_path / "nope.env") == {}


def test_read_parses_pairs_comments_quotes_and_export(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "CF_API_TOKEN=abc123",
                'QUOTED="with spaces"',
                "SINGLE='sq'",
                "export EXPORTED=xyz",
                "NOT_A_PAIR",
            ]
        )
    )
    vals = read_env_file(env)
    assert vals["CF_API_TOKEN"] == "abc123"
    assert vals["QUOTED"] == "with spaces"
    assert vals["SINGLE"] == "sq"
    assert vals["EXPORTED"] == "xyz"
    assert "NOT_A_PAIR" not in vals
