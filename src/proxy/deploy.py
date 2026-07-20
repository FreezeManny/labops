from ansible_runner import Runner

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.creds import Creds
from src.proxy.render import render_caddyfile
from src.utils.ansible_runner import run_playbook

# Inventory alias only (single-host run against the proxy).
_ALIAS = "caddy"


def _build_inventory(config: YamlRoot, dest: str) -> dict:
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot deploy the proxy.")
    creds: Creds = config.settings.default_creds

    host_vars: dict = {
        "ansible_host": str(proxy.proxy_location),
        "ansible_user": creds.username,
        "caddyfile_dest": dest,
    }
    if creds.passwd:
        host_vars["ansible_password"] = creds.passwd
        host_vars["ansible_become_password"] = creds.passwd
    if creds.ssh_key_path:
        host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)

    return {"all": {"hosts": {f"{_ALIAS}_{proxy.proxy_location}": host_vars}}}


def _run(playbook: str, config: YamlRoot, dry_run: bool, verbose: bool) -> Runner:
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot deploy the proxy.")

    caddyfile: str = render_caddyfile(config)

    return run_playbook(
        playbook=playbook,
        inventory=_build_inventory(config, proxy.caddyfile_path_remote),
        extravars={"caddyfile_content": caddyfile},
        dry_run=dry_run,
        verbose=verbose,
    )


def sync_proxy(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Render + write the Caddyfile to the proxy host, without reloading Caddy."""
    return _run("proxy/sync.yml", config, dry_run, verbose)


def deploy_proxy(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Render + write the Caddyfile, then reload Caddy (caddy reload, init-agnostic)."""
    return _run("proxy/deploy.yml", config, dry_run, verbose)
