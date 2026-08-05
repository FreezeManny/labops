from ansible_runner import Runner

from models.input_conf.yaml_root import YamlRoot
from models.input_conf.creds import Creds
from models.input_conf.proxy import ProxyDeploy
from src.host.find import find as find_hosts
from src.vm.find import find as find_vms
from src.lxc.find import find as find_lxcs
from src.proxy.render import render_caddyfile
from src.utils.ansible_runner import run_playbook
from src.utils.inventory import pct_host_vars, ssh_host_vars

# Inventory alias only (single-host run against the Caddy target).
_ALIAS = "caddy"


def _require_deploy(config: YamlRoot) -> ProxyDeploy:
    proxy = config.settings.proxy
    if proxy is None:
        raise ValueError("settings.proxy is not configured; cannot reach Caddy.")
    if proxy.deploy is None:
        raise ValueError(
            "settings.proxy.deploy is not configured; set it to sync/deploy the "
            "Caddyfile (target, caddyfile_dest; add a docker: block for docker mode)."
        )
    return proxy.deploy


def _resolve_connection(config: YamlRoot, deploy: ProxyDeploy) -> dict:
    """Resolve ``deploy.target`` to a single inventory host_vars dict.

    An LXC is reached via the pct connection (SSH to its Proxmox node); a VM or
    bare-metal host is reached over direct SSH. Tried most-specific first (LXC
    also matches by vmid), so the namespaces don't collide.
    """
    target: str = deploy.target
    default_creds: Creds = config.settings.default_creds

    # LXC → proxmox_pct_remote via the parent node.
    try:
        pairs = find_lxcs(config, [target])
    except KeyError:
        pairs = []
    if pairs:
        node, lxc_obj = pairs[0]
        creds: Creds = node.creds or default_creds
        return pct_host_vars(str(node.ip), lxc_obj.vmid, creds)

    # VM → direct SSH.
    try:
        vms = find_vms(config, [target])
    except KeyError:
        vms = []
    if vms:
        vm = vms[0]
        creds = vm.creds or default_creds
        return ssh_host_vars(creds, str(vm.ip))

    # Bare-metal / Proxmox host → direct SSH.
    try:
        hosts = find_hosts(config, [target])
    except KeyError:
        hosts = []
    if hosts:
        host = hosts[0]
        creds = host.creds or default_creds
        return ssh_host_vars(creds, str(host.ip))

    raise ValueError(
        f"settings.proxy.deploy.target '{target}' matches no host, VM or LXC in "
        "the config (checked by name, IP and vmid)."
    )


def _build_inventory(config: YamlRoot, deploy: ProxyDeploy) -> dict:
    host_vars = _resolve_connection(config, deploy)
    host_vars["caddyfile_dest"] = deploy.caddyfile_dest
    return {"all": {"hosts": {f"{_ALIAS}_{deploy.target}": host_vars}}}


def _reload_extravars(deploy: ProxyDeploy) -> dict:
    """Vars the reload needs (mode + docker/override details). No Caddyfile."""
    extravars: dict = {"caddy_mode": deploy.mode}
    if deploy.docker is not None and deploy.docker.container:
        extravars["caddy_container"] = deploy.docker.container
        extravars["caddy_container_config"] = deploy.docker.container_caddyfile_path
    # Set only when provided so the playbook can test `is defined`.
    if deploy.reload_command is not None:
        extravars["caddy_reload_command"] = deploy.reload_command
    return extravars


def _run(
    playbook: str,
    config: YamlRoot,
    dry_run: bool,
    verbose: bool,
    *,
    include_caddyfile: bool,
) -> Runner:
    deploy: ProxyDeploy = _require_deploy(config)
    extravars: dict = _reload_extravars(deploy)
    if include_caddyfile:
        # Only rendered when the file is actually shipped (sync/deploy); a bare
        # reload reuses whatever config is already on the target.
        extravars["caddyfile_content"] = render_caddyfile(config)

    return run_playbook(
        playbook=playbook,
        inventory=_build_inventory(config, deploy),
        extravars=extravars,
        dry_run=dry_run,
        verbose=verbose,
    )


def sync_proxy(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Render + write the Caddyfile to the Caddy target, without reloading."""
    return _run("proxy/sync.yml", config, dry_run, verbose, include_caddyfile=True)


def deploy_proxy(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Render + write the Caddyfile, then reload Caddy only if it changed."""
    return _run("proxy/deploy.yml", config, dry_run, verbose, include_caddyfile=True)


def reload_proxy(
    config: YamlRoot, dry_run: bool = False, verbose: bool = False
) -> Runner:
    """Reload Caddy on the target using its on-disk config, without syncing."""
    return _run("proxy/reload.yml", config, dry_run, verbose, include_caddyfile=False)
