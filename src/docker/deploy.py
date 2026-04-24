from ansible_runner.runner import Runner

from models.input_conf.creds import Creds
from src.docker.find import StackResult
from src.docker._common import build_inventory, extravars
from src.utils.ansible_runner import run_playbook


def deploy(result: StackResult, creds: Creds, dry_run: bool = False, verbose: bool = False) -> Runner:
    return run_playbook(
        playbook="docker/deploy.yml",
        inventory=build_inventory(result, creds),
        extravars=extravars(result),
        dry_run=dry_run,
        verbose=verbose,
    )
