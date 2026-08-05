"""Tests for settings.proxy.template — rendering the Caddyfile from a user template.

A custom template either replaces the built-in one outright or extends it and
overrides individual blocks. Either way the render context is the same, and a
template that is broken or references something that does not exist has to fail
as a reported config error rather than as a traceback or a silent gap in the
generated Caddyfile.
"""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from models.input_conf.yaml_root import YamlRoot
from src.proxy import render_caddyfile


def _model(cfg: dict[str, Any], template: Path | None = None) -> YamlRoot:
    if template is not None:
        cfg["settings"]["proxy"]["template"] = str(template)
    return YamlRoot.model_validate(cfg)


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path: Path = tmp_path / name
    path.write_text(body)
    return path


# ─── Replacing the built-in template ──────────────────────────────────────────


def test_custom_template_replaces_the_builtin(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    tpl = _write(tmp_path, "custom.j2", "# just this\n")
    out = render_caddyfile(_model(valid_config_dict, tpl))
    assert out == "# just this\n"
    assert "reverse_proxy" not in out  # nothing of the built-in survives


def test_custom_template_receives_the_render_context(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    tpl = _write(
        tmp_path,
        "custom.j2",
        "suffix={{ proxy_suffix }}\n"
        "plugin={{ tls_plugin }}\n"
        "{% for r in routes %}{{ r.name }} {{ r.host }} {{ r.target }} "
        "{{ r.insecure }} {{ r.accept | join(',') }}\n{% endfor %}",
    )
    out = render_caddyfile(_model(valid_config_dict, tpl))

    assert "suffix=.example.test" in out
    assert "plugin=github.com/caddy-dns/cloudflare" in out
    # edge: no explicit access -> the default list's CIDR.
    assert "edge edge.example.test 10.0.0.4:80 False 10.0.0.0/24" in out


def test_builtin_is_unchanged_when_no_template_is_set(
    valid_config_dict: dict[str, Any],
) -> None:
    out = render_caddyfile(_model(valid_config_dict))
    assert "Managed by labops" in out
    assert "*.example.test {" in out


# ─── Extending the built-in template ──────────────────────────────────────────


def test_template_can_extend_the_builtin_and_override_a_block(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    tpl = _write(
        tmp_path,
        "custom.j2",
        '{% extends "builtin/Caddyfile.j2" %}\n'
        "{% block global_options %}\n{\n\temail me@example.test\n}\n{% endblock %}\n",
    )
    out = render_caddyfile(_model(valid_config_dict, tpl))

    assert "\temail me@example.test" in out
    # Everything not overridden still comes from the built-in template.
    assert "Managed by labops" in out
    assert "reverse_proxy 10.0.0.4:80" in out
    # Global options must precede the site block or Caddy refuses the config.
    assert out.index("email me@example.test") < out.index("*.example.test {")


def test_extending_works_when_the_custom_template_shares_the_builtin_name(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    # The `builtin/` prefix exists for exactly this case: a bare "Caddyfile.j2"
    # would resolve to the custom template itself and recurse.
    tpl = _write(
        tmp_path,
        "Caddyfile.j2",
        '{% extends "builtin/Caddyfile.j2" %}\n'
        '{% block fallback %}\thandle {\n\t\trespond "go away" 410\n\t}\n{% endblock %}\n',
    )
    out = render_caddyfile(_model(valid_config_dict, tpl))

    assert 'respond "go away" 410' in out
    assert "Unknown service" not in out  # the built-in fallback was replaced
    assert "reverse_proxy 10.0.0.4:80" in out


@pytest.mark.parametrize(
    "block", ["header", "global_options", "log", "routes", "extra", "fallback"]
)
def test_every_documented_block_is_overridable(
    block: str, valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    tpl = _write(
        tmp_path,
        "custom.j2",
        f'{{% extends "builtin/Caddyfile.j2" %}}\n'
        f"{{% block {block} %}}MARKER-{block}\n{{% endblock %}}\n",
    )
    out = render_caddyfile(_model(valid_config_dict, tpl))
    assert f"MARKER-{block}" in out


def test_overriding_routes_drops_the_generated_handles(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    tpl = _write(
        tmp_path,
        "custom.j2",
        '{% extends "builtin/Caddyfile.j2" %}\n{% block routes %}{% endblock %}\n',
    )
    out = render_caddyfile(_model(valid_config_dict, tpl))
    assert "reverse_proxy 10.0.0.4:80" not in out
    assert "@edge host" not in out
    assert "Managed by labops" in out


# ─── Failure modes ────────────────────────────────────────────────────────────


def test_template_syntax_error_names_the_file(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    tpl = _write(tmp_path, "broken.j2", "{% for r in routes %}\n{{ r.name }}\n")
    with pytest.raises(ValueError) as excinfo:
        render_caddyfile(_model(valid_config_dict, tpl))
    msg = str(excinfo.value)
    assert "could not render" in msg
    assert str(tpl) in msg


def test_undefined_variable_is_an_error_not_a_blank(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    # StrictUndefined: a typo must not render an empty string into a Caddyfile
    # that then fails only once it reaches the target.
    tpl = _write(tmp_path, "typo.j2", "suffix={{ proxy_sufix }}\n")
    with pytest.raises(ValueError, match="proxy_sufix"):
        render_caddyfile(_model(valid_config_dict, tpl))


def test_missing_template_is_rejected_at_validation(
    valid_config_dict: dict[str, Any], tmp_path: Path
) -> None:
    # FilePath — caught by `labops validate`, long before a deploy.
    with pytest.raises(ValidationError, match="does not point to a file"):
        _model(valid_config_dict, tmp_path / "nope.j2")


def test_relative_template_resolves_against_the_cwd_at_validation(
    valid_config_dict: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # validate_yaml chdirs to the config file's directory, so a relative path in
    # the YAML is relative to the config file. Model-level, that is the cwd.
    _write(tmp_path, "rel.j2", "# relative\n")
    monkeypatch.chdir(tmp_path)
    model = _model(valid_config_dict, Path("rel.j2"))

    assert model.settings.proxy is not None
    assert model.settings.proxy.template is not None
    assert model.settings.proxy.template.is_absolute()  # stored resolved
    assert render_caddyfile(model) == "# relative\n"
