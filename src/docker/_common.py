from models.input_conf.creds import Creds
from src.docker.find import StackResult


def build_inventory(result: StackResult, creds: Creds) -> dict:
    host_vars: dict = {"ansible_user": creds.username}
    if creds.passwd:
        host_vars["ansible_password"] = creds.passwd
        host_vars["ansible_become_password"] = creds.passwd
    if creds.ssh_key_path:
        host_vars["ansible_ssh_private_key_file"] = str(creds.ssh_key_path)
    return {"all": {"hosts": {str(result.target_ip): host_vars}}}


def extravars(result: StackResult) -> dict:
    return {
        "compose_src": str(result.stack.config_path),
        "compose_dest": f"{result.docker_root.rstrip('/')}/{result.stack.name}",
        "stack_name": result.stack.name,
    }
