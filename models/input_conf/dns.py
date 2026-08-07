from ipaddress import IPv4Address
from typing import Literal, Optional

from models.input_conf.custom_types import StrictModel

# Env var the Pi-hole API password is read from, in the .env secret store next to
# the config file (see settings.env_file and src/utils/env_file.py). Mirrors
# TlsProviderSpec.token_env: the secret lives in the store, not in the config.
PIHOLE_PASSWORD_ENV = "PIHOLE_PASSWORD"


class Dns(StrictModel):
    local_dns_suffix: str
    pihole_location: IPv4Address
    api_port: int = 80
    api_scheme: Literal["http", "https"] = "http"
    password: Optional[str] = None

    @property
    def suffix(self) -> str:
        """``local_dns_suffix`` without a leading dot, for joining onto a label.

        Both ``.lab`` and ``lab`` are accepted in the config and mean the same
        thing; normalizing here means a hostname is always exactly one dot away
        from its label.
        """
        return self.local_dns_suffix.lstrip(".")
