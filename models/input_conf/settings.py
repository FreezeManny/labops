from pathlib import Path
from typing import Optional, Dict

from pydantic import Field

from models.input_conf.creds import Creds
from models.input_conf.custom_types import StrictModel
from models.input_conf.dns import Dns
from models.input_conf.paths import ConfigRelativeFile
from models.input_conf.proxy import Proxy
from models.nodes import Selector


class Settings(StrictModel):
    """Everything that is not a node: credentials, the secret store, and the
    optional DNS, proxy and target-set subsystems.

    Only `default_creds` is required. Leaving `dns` or `proxy` out does not
    disable a feature you were using — it means the corresponding commands have
    nothing to act on and say so, rather than guessing.
    """

    default_creds: Creds = Field(
        ...,
        description=(
            "Credentials used for every node that does not carry its own `creds`."
        ),
    )
    env_file: Optional[ConfigRelativeFile] = Field(
        None,
        description=(
            "The secret store labops reads API tokens from. "
            "Defaults to a `.env` next to the config file; set "
            "this to point elsewhere, relative to the config file or absolute. "
            "labops only ever reads it, and it is git-ignored."
        ),
    )
    dns: Optional[Dns] = Field(
        None,
        description=(
            "Local DNS, published to Pi-hole v6. Omit to leave the `dns` "
            "commands with nothing to do."
        ),
    )
    proxy: Optional[Proxy] = Field(
        None,
        description=(
            "The Caddy reverse proxy. Omit to leave the `proxy` commands with "
            "nothing to do; `web_services` entries are then tracked but not "
            "routed."
        ),
    )
    targets: Dict[str, Selector] = Field(
        {},
        description=(
            "Named, reusable selections for `labops update <name>` — the same "
            "four filters as the CLI options. Put the sweeps you run often here "
            "instead of retyping them."
        ),
    )
