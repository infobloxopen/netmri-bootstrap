import os
import json
from dataclasses import dataclass
from infoblox_netmri.client import InfobloxNetMRI

# Note that we cannot just pick latest version because different
# versions of API tend to, well, differ. Here we assume the customer
# uses reasonably recent (7.0+) version of NetMRI.
# Any change in this version must be tested before it's rolled out.
NETMRI_API_VERSION = "3.1"

config_path = None
_config = None
_client = None


def get_default_config_path():
    """By default, load config.json that's next to this file"""
    base_path = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(base_path, 'config.json')


def get_config():
    global config_path
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                   "config.json")
    global _config
    if _config is None:
        with open(config_path, 'r') as config_fh:
            config_data = json.load(config_fh)
        _config = BootstrapperConfig(**config_data)
    return _config


def get_api_client():
    global _client
    conf = get_config()
    if _client is None:
        _client = InfobloxNetMRI(
            conf.host,
            conf.username,
            conf.password,
            use_ssl=conf.use_ssl,
            ssl_verify=conf.ssl_verify,
            api_version=NETMRI_API_VERSION
        )

    return _client


@dataclass
class BootstrapperConfig:
    host: str
    username: str
    password: str
    scripts_root: str
    bootstrap_branch: str
    skip_readonly_objects: bool
    class_paths: dict
    proto: str = "https"
    use_ssl: bool = True
    ssl_verify: bool = False  # Matches default in infoblox_netmri.client

    def __post_init__(self):
        if self.proto == "https":
            self.use_ssl = True
        elif self.proto == "http":
            self.use_ssl = False
        else:
            raise ValueError(f"Invalid protocol {self.proto}")
